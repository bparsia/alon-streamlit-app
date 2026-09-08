# SPARQL serializer for ALOn responsibility queries

Supersedes `docs/sparql_serializer_ABANDONED.md` — that design was
abandoned specifically because negation had no working inline form on the
Konclude/Rasqal build available at the time (`FILTER NOT EXISTS`
syntax-rejected, `MINUS` segfaulted).

**Only `MINUS` was fixed, not `FILTER NOT EXISTS`.** These are two
separate, unrelated SPARQL mechanisms. `FILTER NOT EXISTS` remains
genuinely unimplemented in the `konclude/rasqal` fork — zero lexer/grammar
support, confirmed from scratch (see `gap-001-filter-not-exists-unimplemented`
in `alon_test_suite/findings/`), and nothing this session touched that.
What changed is `MINUS`: three real bugs in the fork's `MINUS` handling
(a fixture bug, a missing Rasqal algebra case, and a Konclude-side
null-pointer crash — see the findings chain
`bug-002-sparql-minus-fixture-was-invalid-syntax` →
`bug-003-sparql-minus-returns-wrong-results` →
`bug-004-konclude-segfault-multithreaded-multitriple-minus`) were found
and fixed, independently re-verified 2026-09-01. With `MINUS` now
correct and stable, it's sufficient on its own to express ALOn's real
compound-negation pattern (`do(sd1) & Xq & ~[]Xq`, the actual `f1`
expansion axiom shape) — verified against the fixed build. `FILTER NOT
EXISTS` was never required for this; the design below uses `MINUS`
exclusively and does not depend on `FILTER NOT EXISTS` becoming available.

The old doc's context/confirmed-facts sections are still accurate and not
repeated here in full — read it for background (why SPARQL over the
existing OWL/realization path, the `ExpanderTransformer` per-backend
duplication pattern, the closed-world/fully-named-individuals property).
This document only covers what changes now that `MINUS` works: the
design is substantially **simpler** than what was scoped before, not just
unblocked.

## What changes with working MINUS

The old design split on whether a construct needed negation:
- `box(inner)`: NOT one query — decompose into two SELECT queries (full
  same-moment relation, inner's satisfying set) plus a **Python
  set-complement step** to compute box's answer locally.
- `negation(inner)` generally: **out of scope**, blocked entirely.
- `free_do_action`'s `Opp2<action>` exclusion: flagged as needing the
  same workaround as `box`, unconfirmed whether it's reachable.

None of that split is needed anymore. Every construct — including `box`
and general negation — compiles to a **single SPARQL query fragment**,
using nested `MINUS` directly, mirroring how `FormulaToOWL` already
handles `box`/`negation` as ordinary recursive cases (`ObjectAllValuesFrom`
/ `ObjectComplementOf`) rather than special-cased escape hatches. This
also means `FormulaToSPARQL`'s top-level interface can be "one query
string per formula" uniformly — no dataclass-with-a-combinator-function
special case for `box`-containing formulas, which the old design required.

**Important scoping note on the `MINUS` shape**: this session's
investigation (`bug-005` in `alon_test_suite`, ultimately a
query-authoring bug, not a reasoner defect — see that finding's full
trace) confirmed that negating a compound sub-pattern via `MINUS`
requires wrapping the *entire already-computed inner pattern* in one more
`MINUS` level, not reusing the inner pattern's own `MINUS` structure
directly as the negation. Concretely, for `box(inner)` = `[]φ`:

```sparql
# box(inner): all same-moment successors satisfy inner
?idx a owl:Thing .
MINUS {
  ?idx alon:same_moment ?j .
  ?j <inner's pattern, substituting ?j for ?idx>
  MINUS { <inner's pattern> }   # only needed if inner itself contains negation
}
```

and for `negation(inner)` generally — wrapping *whatever pattern
`inner` compiles to* in one more outer `MINUS`:

```sparql
# negation(inner): idx does NOT satisfy inner
?idx a owl:Thing .
MINUS {
  ?idx a owl:Thing .
  <inner's own compiled pattern, unmodified>
}
```

This "reuse inner's pattern under one more MINUS layer" rule is the thing
bug-005 got wrong (reused `box`'s own MINUS body directly as the negated
form, which computes something else entirely — see that finding for the
worked-out semantics). `FormulaToSPARQL`'s `negation` and `box` methods
must both follow this exact wrapping shape; this is the one place in the
design worth extra unit-test scrutiny given a real mistake was already
made here once.

## Updated per-construct mapping

| Construct | OWL (existing) | SPARQL (new) |
|---|---|---|
| `prop(p)` | `Class IRI=".../p"` | `?idx a alon:p .` |
| `do_action(a)` | `Class`/`ObjectIntersectionOf` | `?idx a alon:a .` (group action: one triple per conjunct, `_intersect`-style) |
| `free_do_action(a)` | `a ⊓ ¬Opp2a` | `?idx a alon:a . MINUS { ?idx a alon:Opp2a . }` — same negation-of-atom shape as `negation`, confirmed real (appears 3x in 3.1.mmd's real expanded axioms, always as `free_do(a)` inside a `pdl_box`'s implication, never bare) |
| `conjunction` | `ObjectIntersectionOf` | concatenate patterns (SPARQL AND is juxtaposition) |
| `disjunction` | `ObjectUnionOf` | `{ pattern1 } UNION { pattern2 }` (confirmed appears in real axioms, 5/36 in the 3.1.mmd sample) |
| `negation(inner)` | `ObjectComplementOf` | outer `MINUS` wrapping inner's own pattern verbatim — see wrapping rule above. **No longer out of scope.** |
| `implication(A, B)` | reduces to `¬A ∨ B` | same reduction, using `negation`+`disjunction` above (both now supported) |
| `next(inner)` | `ObjectSomeValuesFrom(succ, inner)` | `?idx alon:succ ?idxN . <inner on ?idxN>` (no negation needed, `succ` functional) |
| `diamond(inner)` | `ObjectSomeValuesFrom(same_moment, inner)` | `?idx alon:same_moment ?idxN . <inner on ?idxN>` (confirmed: never appears directly in real expanded axioms for 3.1.mmd, but grammar-valid, keep supported) |
| `box(inner)` | `ObjectAllValuesFrom(same_moment, inner)` | single query, nested `MINUS` — see wrapping rule above. **No longer a two-query decomposition + Python combinator.** |
| `top`/`bottom` | `owl:Thing`/`owl:Nothing` | always-true empty pattern / always-false (query returns no rows, e.g. `FILTER(false)` or an unsatisfiable triple pattern) |

`biconditional` reduces to `(A→B) ∧ (B→A)` exactly as `FormulaToOWL`
already does — now fully reachable since implication/negation both work.

Nothing in this table uses `FILTER NOT EXISTS`. If a future ALOn query
shape is found that genuinely can't be expressed via `MINUS`'s
set-difference semantics (not yet encountered), `FILTER NOT EXISTS`
remains the fallback to revisit — but it would require the from-scratch
Rasqal grammar/lexer/evaluator work scoped in `gap-001`, which has not
been started.

## Design

### 1. No `SparqlExpanderTransformer` needed — reuse `ExpanderTransformer` directly

The old design (and this doc's own earlier draft) assumed a per-backend
expander subclass would be needed, mirroring
`PyDatalogExpanderTransformer`. **Checked directly against the source,
not assumed: this is wrong.** `ExpanderTransformer`
(`alo_translator/parsers/expander_transformer.py`) is entirely
target-language-agnostic — every method builds plain formula *strings*
(`"~[]Xq"`, `"do(sd1)"`) and stores `"expansion => name"` axiom strings;
nothing in it touches OWL/XML or Datalog syntax at all. `OWLSerializer`
already uses the bare `ExpanderTransformer` directly with no subclass
(`_make_expander()`, `owl.py:595`) — SPARQL can do the same.

`PyDatalogExpanderTransformer` exists for a *different* reason than "each
backend needs its own expander": pyDatalog specifically cannot express
disjunction or implication as a formula (`self.axioms.add(...)` strings
containing `v`/`->` don't survive into valid pyDatalog rules), so it
overrides `pdl_box` etc. to avoid ever generating those operators,
replacing them with named-implication tricks. SPARQL has no such
limitation — per the per-construct mapping above, `disjunction` compiles
to `UNION` and `implication` reduces to negation+disjunction, both
supported via `MINUS`. So SPARQL's expansion needs are closer to OWL's
(no restrictions) than to pyDatalog's (restricted), and no subclass is
needed: `FormulaToSPARQL` (below) can consume axioms from a bare
`ExpanderTransformer`, exactly as `OWLSerializer` does.

### 2. `FormulaToSPARQL` transformer — new file `alo_translator/serializers/sparql.py`

A `lark.Transformer` mirroring `FormulaToOWL`'s shape, fed post-expansion
primitive-formula strings, emitting SPARQL graph-pattern fragments
(strings), parameterized by a single "current index" variable threaded
through recursively (start at `?idx0`, fresh `?idxN` per `next`/`diamond`/
`box` nesting level — reuse `datalog.py`'s `_fresh_var()`/
`_substitute_var()` pattern directly, same mechanism, different target
language).

Given the per-construct mapping above, every formula (box-free or not,
negation-containing or not) compiles to **one query fragment** — a
`WHERE` clause body used inside `SELECT ?idx0 WHERE {...}`. No composite
return type needed; `FormulaToSPARQL.transform(tree)` returns a plain
string, same interface as `FormulaToOWL`/`FormulaToDatalog`.

Top-level entry point: given a `Query.expanded_ast`, produce the single
`SELECT ?idx0 WHERE {...}` query that computes the full set of
individuals satisfying that formula (not bound to one evaluation point)
— membership for a specific eval point (e.g. `alon:m_h1`) is then checked
locally in Python against the result set, exactly like the OWL/realization
path already does via `run_analysis_konclude_layered`.

### 3. Konclude SPARQL execution — extend `alo_translator/reasoners/konclude.py`

Unchanged from the old design:
- Add `ReasoningMode.SPARQL` to the enum in `alo_translator/reasoners/base.py`.
- Add a SPARQL branch in `KoncludeAdapter.run()`: build
  `[konclude_path, "sparqlfile", "-s", query_file, "-i", ontology_file,
  "-o", output_file, "-w", threads]`.
- Add a `bound_individuals: Optional[Set[str]]` field to
  `ReasoningResult` (additive), populated by parsing Konclude's SPARQL
  XML result format (`<results><result><binding name="idx0">
  <uri>...</uri></binding></result>...`, confirmed empirically against
  the real fixed build this session, same format the old doc already
  confirmed on the pre-fix build).

Do NOT use `ASK` anywhere — still confirmed broken (see
`bug-001-sparql-ask-always-true` in `alon_test_suite/findings/`, gives
wrong answers in both directions, unrelated to and unaffected by the
MINUS fixes). Every query must be `SELECT`-based.

### 4. Analysis entry point — new function in `streamlit_app/utils.py`, e.g. `run_analysis_konclude_sparql_layered`

Mirrors `run_analysis_konclude_layered`'s loop-over-`model.evaluations`
shape: build the OWL ontology once per eval point exactly as today
(unchanged), then for each `Query` in `model.queries`, generate its
**single** SPARQL query via `FormulaToSPARQL` (no more "one or two
queries depending on whether `box` appears" branching the old design
needed), run it via the new Konclude SPARQL mode, and check whether the
specific eval-point individual (e.g. `alon:m_h1`) is in the resulting
satisfying set; collect `query_id` into the overall satisfied set if so.
This is now exactly N SPARQL queries per eval point (one per
responsibility query, no `box`-doubling) — simpler accounting than the
old design's "at least N, more for box-containing queries."

## Verification plan

Same discipline as the old doc, now applied to a design that should
actually work:

1. Before writing `FormulaToSPARQL`: dump real expansion axioms for a
   representative query set (done for 3.1.mmd this session as part of
   picking this back up — 36 axioms, 15 contain `~[]`, 15 contain plain
   `[]`, 3 contain `free_do`, 5 contain disjunction, 0 contain `<>`
   directly). Repeat for isabella.mmd or another model with different
   structure before considering the construct-coverage check complete.
2. Unit test `FormulaToSPARQL` directly: construct small primitive-formula
   strings for each construct (prop, do_action, free_do_action,
   conjunction, disjunction, negation, next, diamond, box) and check the
   generated SPARQL string shape — pay particular attention to `negation`
   and `box`'s wrapping rule given bug-005's mistake was exactly a
   misapplication of that rule.
3. End-to-end: pick 3.1.mmd and a known-correct query (e.g. `pres_1_q` at
   `m/h1`), run through the new SPARQL path, confirm the resulting
   satisfying-individual set (and eval-point membership) matches the
   already-verified pyDatalog/OWL-realization result for the same query
   — cross-backend agreement check.
4. Do NOT speculate about SPARQL execution performance vs. realization
   performance without measuring both (standing rule, `CLAUDE.md`) —
   applies here exactly as much as it did to the Konclude realization
   investigation earlier this session.
5. Never use `ASK` (see above) — if reconsidered later, re-test
   correctness first, don't assume fixed.

## Not yet done

This document is a design, not an implementation. Nothing described here
has been coded yet as of this writing. Next concrete step: write
`SparqlExpanderTransformer` (step 1), porting `ExpanderTransformer`'s
expansion logic method-by-method, checked against the same real
expansion-axiom dump used to validate this design's construct coverage.
