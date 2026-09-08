# MSC (minimal sufficient cause) as a first-class operator — design doc

Status: draft, not yet implemented. Edit freely.

## Definitions

Paper (`papers/2026Fear/paper_mirror/2Prelims.tex:187-231`):

```
msCause(a, φ) := [a]φ  ∧  ⋀_{K ⊊ agents(a)} ¬[proj(a,K)]φ
nessCause(a, φ)  ⟺  ∃b. a ⊑ b ⊑ a_h  ∧  msCause(b, φ)
```

`msc(a, φ)` is a **membership test**: is `a` itself (exactly, not up to
some superset) a minimal sufficient set for φ — sufficient (`[a]φ`) and
minimal (no proper subset of `a`, including ∅, is also sufficient). Same
`(action, φ)` argument shape as `ness`/`but`. Entirely in-reasoner, same
as every other operator: the expander builds one formula string
expressing sufficiency + minimality, registers it as one axiom, the
reasoner evaluates it.

## 1. Expansion plan for `msc`

`ExpanderTransformer.msc(self, items)`, in
`alo_translator/parsers/expander_transformer.py`, alongside `ness()`:

- Parse `a` into `target_actions: Set[Tuple[str,str]]` (existing
  `_parse_action_str`, same as `ness`).
- Sufficiency: build `[a]φ`, parse/transform to get `sufficient_name`
  (same as `ness`'s per-candidate step, `expander_transformer.py:430-439`).
- Minimality: enumerate proper subsets `K ⊊ a` (including `K=∅` when
  `ness_empty_sufficient`, same as `ness`'s `proper_subsets` loop,
  lines 449-482) and build the same named-negation conjunction `ness`
  already builds.
- Combine: `do(a) & [a]φ & ⋀_{K⊊a} ¬[K]φ`, one axiom, name returned.

This is the same sufficiency+minimality logic `ness` already runs **per
candidate** inside its powerset loop — `msc` runs it once, for `a` only.

Grammar: `msc: "msc" "(" action_expr "," formula ")"` in
`alon_grammar_clean.lark`, same shape as `ness`.

Serializers: add `msc` to the `_must_not_appear` guard list in `owl.py`,
`datalog.py`, `sparql.py` (same position as every other defined operator
in all three) — no other serializer work; `msc(a, φ)` expands to a plain
boolean-backed axiom exactly like `ness`/`but_for`.

Query generation: add `"msc"` to the existing `but`/`ness` branch in
`query_generation.py::_generate_responsibility_queries()` — same
per-agent/coalition loop. `format_results_table` gets one more boolean
tick-column.

## 2. Three variants of `res`, kept side by side

`res(a,φ)` today (`expander_transformer.py:571-609`) is one axiom with
five conjuncts: `do(a) & expected_result(a,φ) & ness(a,φ) & ~[]Xφ &
~[]do(a)`. `res()` builds the `ness(...)` sub-expression, parses it,
transforms it, and splices the returned axiom name directly into its own
conjunction (line 604-607) — `ness` has to keep behaving like every other
operator (one axiom, one name) for this to keep working as-is.

Three variants to build and compare, not one replacing another:

1. **Current fully-inline `res`** — unchanged. `ness` computed by its
   existing powerset search. Baseline for regression comparison.
2. **MSC-based fully-inline `res`** — same one-axiom shape as (1), same
   splicing pattern in `res()`, but `ness`'s own expansion is rebuilt in
   terms of `msc`: `ness(a,φ)` = disjunction over supersets `b ⊇ a` of
   `msc(b,φ)`'s sufficiency+minimality formula. Still fully in-reasoner,
   still one axiom, still returns a name `res()` splices in exactly like
   today. Expected to be logically equivalent to (1) — this is the
   regression check (§3).
3. **`res_candidate` + `ness` as a post-step, outside the reasoner** —
   structurally different, not a variant of `ness`'s internals. Split
   `res`'s conjuncts:
   - `res_candidate(a,φ)` := `do(a) & expected_result(a,φ) & ~[]Xφ &
     ~[]do(a)` — one axiom, everything `res` needs except `ness`. This is
     what actually gets sent to the reasoner.
   - `ness(a,φ)` computed separately (however — current powerset search,
     or MSC-based, doesn't matter for this variant's structure) and
     combined with `res_candidate`'s reasoner-returned boolean via a
     plain Python `AND`, outside the axiom entirely.
   - `res(a,φ) := res_candidate(a,φ) AND ness(a,φ)`, assembled after both
     pieces are known, not as one axiom.

## 3. Regression testing

- (1) vs (2): confirm byte-identical satisfied-query sets across the
  full test-suite model set (3.1, 3.5, 3.6, 3.7, isabella) — this is the
  correctness bar for "MSC-based ness is a valid reformulation," not just
  "it runs."
- `docs/cornercases.md`'s `ness_empty_sufficient` worked example
  (`but(sd1,q)` true, `ness(sd1,q)` false) — re-run against variant (2)
  specifically, since the paper's `msCause` minimality conjunction
  includes `K=∅` while `nessCause`'s own per-witness conjunction as
  literally written excludes it (they reconcile via `b` ranging over all
  enclosing supersets — worth this direct check rather than trusting the
  reconciliation unverified).
- (3) vs (1)/(2): confirm `res` results also match — this variant
  computes the same logical conjunction, just split across a
  reasoner-call boundary, so it should agree exactly.
- Sanity invariant: for any coalition, `msc(a,φ)` true implies
  `ness(a,φ)` true for that same `a` (a is trivially a superset of
  itself) — assert on real models in all variants.

## Explicitly out of scope for this pass

- `GroupAction`/`Action` gaining `__hash__`/subset-checking methods —
  keep using raw `Tuple[str,str]` sets, matching `ness`'s current
  representation.
- Any witness-listing output structure (list of all MSCs at an eval
  index) — not needed for the table, which only wants one boolean per
  coalition.
- A batched/single-query retrieval form for MSC (e.g. one SPARQL query
  returning all qualifying group actions at once) — possible future
  optimization, not part of this design.

## Files to touch

- `alo_translator/parsers/alon_grammar_clean.lark` — `msc` grammar rule
- `alo_translator/parsers/expander_transformer.py` — add `msc()`; add
  variant-(2) `ness()` (MSC-based disjunction-over-supersets); add
  `res_candidate()` for variant (3)
- `alo_translator/parsers/pydatalog_expander_transformer.py` — same,
  pyDatalog-safe
- `alo_translator/serializers/owl.py`, `datalog.py`, `sparql.py` — add
  `msc` (and `res_candidate` if it needs its own guard entry) to each
  `_must_not_appear` list
- `alo_translator/query_generation.py` — add `"msc"` to the `but`/`ness`
  branch; figure out how variant (3)'s post-step composition plugs into
  query generation/results assembly (not yet designed — `res_candidate`
  and `ness` need to be run and combined by whatever calls
  `generate_queries`/`evaluate`, not inside the expander)
