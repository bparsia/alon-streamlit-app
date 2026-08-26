# SPARQL serializer for ALOn responsibility queries

## Context

Thread #1 from the six open work threads (see `project_six_threads_2026-08` memory) — "more ALOn translations, esp. SPARQL" — has been parked pending the compiler-pipeline staging fix. The user pointed out this gate doesn't actually apply to SPARQL: unlike a TBox-based translation (which would need real analysis of the model before serializing, e.g. building GCIs), SPARQL queries run directly against the *same* OWL ABox/TBox the existing `OWLSerializer` already produces — the model-serialization half of the pipeline needs zero changes. Konclude already supports SPARQL execution (`sparqlfile` mode), so there's a ready-made execution engine, not just a query-language target.

Confirmed by reading the actual code (not assumed):
- `OWLSerializer` serializes the model (moments/histories as named individuals, `succ`/`same_moment` properties, action/proposition `ClassAssertion`s) completely independently of any query. This is reusable as-is for SPARQL — a SPARQL backend loads the identical `.owl` file.
- Today, each *query* (`pres_1_q`, `outcome_m_h1_q`, etc.) becomes an OWL `SubClassOf(formula, query_id)` axiom via `FormulaToOWL` (`alo_translator/serializers/owl.py`), turning "does formula φ hold at this world" into "is this individual classified under a fresh named class" — then `run_analysis_konclude_layered` (`streamlit_app/utils.py`) runs full realization and filters the result down to the one individual (`m_h1` etc.) actually being asked about, discarding results for every other individual. This SubClassOf-injection approach is what SPARQL needs to *replace*, not reuse — SPARQL should ask the question directly (`ASK { ... }` bound to the one individual of interest), not inject a class into the ontology and realize everything.
- `FormulaNode.expand()` (`alo_translator/model/formula.py`) is model-independent and already produces the fully-expanded primitive tree (only box/diamond/next/conjunction/disjunction/negation/do_action/free_do_action/prop/top/bottom remain — pres/sres/res/dxstit/but/ness/opposing/pdl_box/pdl_diamond never appear post-expansion, confirmed by `FormulaToOWL`'s `_must_not_appear` guards). This tree is exactly what a new `FormulaToSPARQL` transformer walks — fully shared with the OWL path, no duplication of the actual responsibility-operator semantics.
- The closed-world/named-individuals property the user flagged is real and important: every moment/history pair is an explicit named individual (confirmed via `_add_action_assertions`/`_add_proposition_assertions` emitting plain `ClassAssertion(ActionName/PropName, individual)` triples — no anonymous individuals anywhere in this ontology). So "for all successors" (`box`, via `same_moment`) is never open-world universal quantification over an unbounded domain — it's checking a known, enumerable, finite set of same-moment individuals, which SPARQL's `FILTER NOT EXISTS`/`MINUS` (bounded, closed-world negation) expresses directly and correctly, unlike genuine OWL-style universal quantification which would need to worry about unnamed individuals.
- Compared the equivalent already-solved problem in `alo_translator/serializers/datalog.py`. NOTE: Datalog *does* support real recursion via named IDB predicates (e.g. `same_moment(I,J) <= same_moment(I,K) & same_moment(K,J)`, a genuine transitive-closure rule already in this codebase) — that is NOT the constraint at play here. The actual shared constraint between Datalog and SPARQL is: **neither has a direct universal-quantification operator** ("for all X, P(X)" isn't a primitive either language can express directly; both only have existential-style pattern matching plus negation). `box` (universal over same-moment individuals) is the one construct that needs this, and both languages solve it the same way — via double-negation ("no X exists for which NOT P(X)"), which is logically equivalent to universal quantification when the domain is bounded, i.e. a fixed, finite, fully-named set of individuals (true here, confirmed no anonymous individuals anywhere in this ontology).
  - Datalog's specific mechanism: `next(items)` → `succ(I,J) & inner(J)` (simple — `succ` is a `FunctionalObjectProperty`, exactly one successor, so no negation trick needed); `diamond(items)` → `same_moment(I,J) & inner(J)` (plain existential, no negation needed); `box(items)` → double-negation via a **fresh named helper IDB predicate** (`box_violation_N(I) <= same_moment(I,J) & ~inner(J)`, then `box` returns `~box_violation_N(I)`) — using a named predicate here is a Datalog *convenience* (lets the double-negation be defined once and reused/composed cleanly), not a requirement of the double-negation technique itself.
  - SPARQL's equivalent: `FILTER NOT EXISTS { ?j same_moment ?i . FILTER NOT EXISTS { <inner pattern on ?j> } }` — same double-negation idea, but SPARQL has no named/reusable rule mechanism, so each `box` occurrence must be written inline as a nested subquery/filter at its own position in the formula tree rather than factored into a shared named predicate. Formulas here are shallow post-expansion (box/diamond/next don't nest more than a few levels deep), so the resulting nested-filter SPARQL is expected to stay readable — flagging this as the one construct worth double-checking carefully once real queries are generated, not as a blocking problem.

## Goal

Build a `FormulaToSPARQL` transformer (parallel to `FormulaToOWL`) plus a `KoncludeAdapter` SPARQL execution path, so ALOn responsibility queries can be answered by running SPARQL `ASK` queries against the *unmodified* model ontology via Konclude's `sparqlfile` mode, instead of injecting per-query `SubClassOf` axioms and running full realization.

## Design

### 1. `FormulaToSPARQL` transformer — new file `alo_translator/serializers/sparql.py`

A `lark.Transformer` mirroring `FormulaToOWL`'s shape but emitting SPARQL graph-pattern fragments (strings) instead of OWL/XML, parameterized by a single "current index" variable threaded through recursively (start at `?idx0`, fresh `?idxN` per `next`/`box`/`diamond` nesting level — same fresh-variable approach `datalog.py` already uses via `_fresh_var()`/`_substitute_var()`, reusable pattern, not a new idea).

Per-construct mapping (each returns a WHERE-clause fragment referencing its bound index variable):

| Construct | OWL (existing) | SPARQL (new) |
|---|---|---|
| `prop(p)` | `Class IRI=".../p"` (ClassAssertion check via realization) | `?idx a alon:p .` |
| `do_action(a)` / `free_do_action(a)` | `Class`/`ObjectIntersectionOf` with `Opp2<a>` exclusion | `?idx a alon:a .` / `?idx a alon:a . FILTER NOT EXISTS { ?idx a alon:Opp2a }` |
| `conjunction` | `ObjectIntersectionOf` | concatenate patterns (SPARQL AND is juxtaposition) |
| `disjunction` | `ObjectUnionOf` | `{ pattern1 } UNION { pattern2 }` |
| `negation` | `ObjectComplementOf` | `FILTER NOT EXISTS { pattern }` |
| `next(inner)` | `ObjectAllValuesFrom(succ, inner)` | `?idx alon:succ ?idxN . <inner on ?idxN>` (no negation needed — `succ` is functional, confirmed `FunctionalObjectProperty` in the OWL output) |
| `diamond(inner)` | `ObjectSomeValuesFrom(same_moment, inner)` | `?idx alon:same_moment ?idxN . <inner on ?idxN>` |
| `box(inner)` | `ObjectAllValuesFrom(same_moment, inner)` | `FILTER NOT EXISTS { ?idx alon:same_moment ?idxN . <negated inner on ?idxN> }` (double-negation, per Datalog precedent above) |
| `top`/`bottom` | `owl:Thing`/`owl:Nothing` | always-true empty pattern / always-false `FILTER(false)` |

`biconditional`/`implication` reduce to conjunction/disjunction/negation combinations exactly as `FormulaToOWL` already does (reuse that reduction logic, it's construct-agnostic).

Top-level entry point: given a `Query.expanded_ast` and a specific evaluation individual IRI (e.g. `alon:m_h1`), produce a complete `ASK { <pattern with ?idx0 bound to the given IRI via VALUES or direct substitution> }` query string.

### 2. Konclude SPARQL execution — extend `alo_translator/reasoners/konclude.py`

- Add `ReasoningMode.SPARQL` to the enum in `alo_translator/reasoners/base.py`.
- Add a SPARQL branch in `KoncludeAdapter.run()`: build `[konclude_path, "sparqlfile", "-s", query_file, "-i", ontology_file, "-o", output_file, "-w", threads]` instead of the current `realize`/`classification` command, matching the existing `sparqlfile -s ... -i ... -o ...` usage confirmed via `Konclude --help`.
- New result shape needed: a SPARQL `ASK` result is a single boolean, not `Dict[str, Set[str]]` (`individual_types`) like realization produces. Add a `boolean_result: Optional[bool]` field to `ReasoningResult` (additive, doesn't disturb the existing realization path) and populate it by parsing Konclude's SPARQL XML result format (`<boolean>true</boolean>`, standard SPARQL 1.1 XML Results Format — Konclude's `sparqlfile` output format needs a quick empirical check against a real run before assuming the exact tag structure, since this hasn't been tested yet).

### 3. Analysis entry point — new function in `streamlit_app/utils.py`, e.g. `run_analysis_konclude_sparql_layered`

Mirrors `run_analysis_konclude_layered`'s loop-over-`model.evaluations` shape, but per query: build the OWL ontology once per eval point exactly as today (reused, unchanged), then for each `Query` in `model.queries`, generate its SPARQL `ASK` string via `FormulaToSPARQL`, run it via the new Konclude SPARQL mode, and collect `query_id` into the satisfied set if the boolean result is `true`. This is N SPARQL queries per eval point (one per responsibility query) rather than 1 realization call — a real trade-off (more Konclude invocations) worth measuring once built, not assumed to be better or worse than realization.

## Verification

- Unit test `FormulaToSPARQL` directly (mirroring how `FormulaToOWL` is likely tested, or via the same manual-repro style used earlier this session for the `_sanitize_name` bug): construct small expanded `FormulaNode` trees for each construct (prop, do_action, negation, conjunction, disjunction, next, diamond, box) and check the generated SPARQL string shape/structure.
- End-to-end: pick one existing model (3.1.mmd) and one known-correct query (e.g. `pres_1_q` at `m/h1`), run it through the new SPARQL path, and confirm the boolean result matches the already-verified pyDatalog/OWL-realization result for that same query (cross-backend agreement check, same pattern used to verify the OWL sanitize bug fix and the Konclude load-sensitivity findings this session).
- Confirm Konclude's actual SPARQL XML output format empirically (run a trivial hand-written `ASK` query against a real serialized `.owl` file via `sparqlfile` mode) before finalizing the `boolean_result` parsing logic in step 2 — don't guess the XML shape.
- Do NOT speculate about SPARQL execution performance vs. realization performance without measuring both — per the standing no-reasoner-hypothesizing rule (`CLAUDE.md`, `feedback_no_reasoner_hypothesizing` memory), this applies to Konclude's SPARQL mode exactly as much as its realization mode.
