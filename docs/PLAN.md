# ALOn Toolkit — Open Issues & Roadmap

This document consolidates all known open issues, design decisions pending implementation,
and planned refactors. Update it as work is completed or priorities shift.

Last updated: 2026-07-16

---

## Execution Order

**P3 → (P4a in parallel) → P1 → P2**, then P5/P6/P7/P8 in any order.

- **P3 first** — implement remaining semantics before the compiler pipeline, so P1 has the
  full feature set to analyse and tag.
- **P4a in parallel with P3** — test models exercising new features are needed to develop and
  verify P3. Demo models (P4b) follow once features are stable.
- **P1 after P3** — semantic analysis + serialiser tagging is then complete, including tagging
  Datalog as incompatible with most TBox axioms.
- **P2 after P1+P3** — first new serialiser in a while; properly gated by P1 compatibility
  tagging. SPARQL may need different reasoner infrastructure (query loop rather than single-file
  submission) — best deferred until the pipeline is stable.

---

## Priority 1 — Compiler Pipeline (Semantic Analysis)

**Design doc:** `docs/compiler_pipeline.md`
**Status:** Designed, not implemented.

The current pipeline is: parse → generate, with no validation layer between them. The plan is:

```
parse() → RawModel → analyse() → SemanticModel (+ issues[]) → generate(target)
```

### What to implement

1. **`MomentRole` computation** — TD, leaf/root/intermediate, depth, same_moment cardinality
2. **`signature()`** — propositional atom extraction from labels + queries
3. **Moment label checks**
   - E001: action-modal formula at a leaf moment
   - W001: leaf missing literal for signature atom (underspecified valuation)
   - W002: `[]do(a)` at non-leaf where some CGA lacks `a`
   - *Note: complex (non-literal) proposition labels are handled by per-moment available actions
     and TBox axioms (see Priority 3 — Remaining Semantics). Compatibility is surfaced via
     serialiser tagging, not as issues on the model itself.*
4. **Query × evaluation index compatibility**
   - E004: `Xφ` at leaf index (no successors)
   - W004: `[]φ`/`<>φ` at isolated index (vacuously true/false)
   - W005: responsibility operator at leaf
   - W006: modal depth of query exceeds model TD from eval index
   - W007: `do(a)` at index where `a` is not asserted
5. **`CGACoverage`** — completeness check (all agent×action combos present at each moment)
6. **Target compatibility / serialiser tagging**
   - Semantic analysis tags the `SemanticModel` with serialiser compatibility, not the serialiser
     itself. The result is a "complexity report" — features present in the model and which
     serialisers support them.
   - OWL: warn if any leaf lacks `¬∃succ.⊤` assertion (open-world successor problem)
   - OWL: note if TBox-style axioms present (supported)
   - Datalog: flag if any moment label is non-literal (unsupported — see P3)
   - Datalog: flag if modal depth of query > TD
7. **`QueryResult` provenance** — distinguish structural false vs semantic false in UI

### Entry points
- **Compiler:** `parse → analyse → generate`, errors block generation
- **Linter (standalone):** `parse → analyse(queries=[], eval_points=[])` — surfaces issues without running
- **Query advisor:** `analyse(queries=[q], eval_points=[...])` — compatibility check for a specific query×index

---

## Priority 2 — DL-Safe Rule OWL Serialisation

**Design doc:** `docs/owl_rules_investigation.md`
**Status:** Investigated, not implemented.

Current OWL serialiser uses class expressions (SubClassOf axioms). This works with Konclude but
produces a non-standard encoding. The DL-safe rule encoding would express the same semantics
using SWRL or RIF rules, enabling use with rule-based reasoners and making the axioms more
readable.

Key question: which constructs require DL-safe rules vs pure OWL-DL axioms?

---

## Priority 3 — Remaining Semantics

Features needed to reach full ALOn expressivity.

### 3a. Per-moment available actions — LARGELY DONE

Per-moment actions were already represented in `MomentNode.available_actions` and
`HistoryPath.actions_at`. Work completed this cycle:

- `moment` field added to `ResponsibilityConfig` — agent sets now restricted to agents
  active at the evaluation moment via `available_actions_at(moment)`
- `but`/`ness` action lookup uses `(moment, history)` index, not `complete_actions()`
- `_sanitize_id` handles `<>` and `[]` — modal operators in target propositions no longer
  produce invalid XML IRIs or Datalog predicate names
- OWL serializer silent failures converted to hard errors
- Outcome display fixed — checks successor of eval moment (Xφ), not leaf
- `res_analyse` YAML syntax confirmed and working for multi-point, multi-outcome analysis
- TD=2 Isabella model (`depth2_example.mmd`) working end-to-end in both serialisers

**Remaining:** `but`-for vacuity — when only one agent acts at a moment, the PDL box
counterfactual `[γ']¬φ` is trivially true (material conditional with false antecedent at the
current index). This is a known semantic issue; fix requires evaluating the counterfactual
across same-moment indices where γ' is actually performed. Not yet fixed.

### 3b. TBox-style global axioms

Axioms with global effect (e.g. `do(sd1) → Xq`) that apply across all indices rather than
being asserted at a specific moment. These are likely OWL-only (Datalog would need NAF-safe
rewriting). Semantic analysis tags models containing TBox axioms as OWL-only.

**Status:** Not started.

---

## Priority 4 — Model Library

Two distinct purposes requiring different model designs:

### 4a. Test models
Minimal models that exercise specific features and have known ground-truth results (verified
against Konclude baselines). Drive regression testing and serialiser compatibility checks.
Feature matrix (which features each existing model exercises) should be generated first to
identify gaps.

TD=2 Isabella models (`depth2_example.mmd` and siblings) exist and run end-to-end but are
not yet captured in the result registry. Formal capture + verification pending once `but`
vacuity issue is resolved.

### 4b. Demo / experiment models
Richer models illustrating philosophical or legal scenarios — used in papers, the Streamlit
app, and the alo_docs system. Should include expected-result annotations for the docs renderer.
Examples: theories 3.1, 3.5, 3.6, 3.7 plus new scenarios.

---

## Priority 5 — IDE

The Streamlit app is the current IDE. Planned improvements:

- Model skeleton generator (given agents/actions/TD, produce a blank Mermaid diagram)
- Ridge naming scheme for moments (systematic naming for branching structures)
- Query advisor UI (surface semantic analysis warnings interactively)
- Better error display (parse errors, semantic issues, serialiser compatibility)

---

## Priority 6 — Reasoning Services

**Status:** Not started.

### 6a. All-points evaluation
The app currently evaluates at a single (moment, history) pair. All-points runs every query
at every valid index and aggregates — showing which responsibility claims hold globally vs
locally, and at which indices each claim first/last holds.

### 6b. Bulk services (query × index matrix)
Bulk versions of the single-point pipeline: compute the full query × index result matrix in
one pass. Subsumes 6a. Useful for model checking and for populating the experiment results
table without repeated invocations.

### 6c. Model checking
Given a formula, find all indices where it holds. Dual: find counterexamples. Supports
checking universal/existential claims over the model ("does every history satisfy pres?").

### 6d. Explanation
Given a query result (true or false), produce a witness or counterexample trace:
- For **true**: the assignment of actions/propositions that satisfies the formula
- For **false**: the minimal substructure that blocks satisfaction (why it fails)
- Particularly useful for causal queries (but/ness): show the set S that witnesses NESS

### 6e. Entailment / query comparison
Given two queries, determine whether one entails the other across all points in the model.
Useful for comparing responsibility notions (e.g. does sres always imply pres here?).

---

## Priority 7 — Computational Experiment Pipeline Refresh

**Status:** Exists in `deontickit/alon_experiments/`, needs migration and modernisation.

The experiment pipeline was used to produce the baseline results in the AAAI supplement.
Needs:
- Clean implementation in `alon-streamlit-app` (under `alo_translator/experiments/`)
- Runner that can: (a) run all theories, (b) compare OWL vs Datalog results,
  (c) produce a results table in one command
- Regression tests against Konclude baselines (`tests/fixtures/konclude_baselines.json`)

---

## Priority 8 — Repo Housekeeping

- Rename `alon-streamlit-app` repo to `alon-toolkit` or similar (optional/cosmetic)
- `deontickit/alon_experiments/` is now legacy — no further development there

---

## Codebase Cleanup — DONE

- **3a.** TD=1 special pathway removed — everything goes through ALOModel / layered pipeline
- **3b.** TOML model input removed — Mermaid+YAML is the only format
- **3c.** Debug print statements removed (files deleted in serialiser consolidation)
- **3d.** Datalog complex-prop rejection — subsumed by Priority 1 serialiser tagging
- **Serialiser consolidation** — 5 files → `owl.py` + `datalog.py` (-907 lines)
- **Alias display bug** — YAML integer keys stringified at parse time
- **Formula-stable baselines** — tests compare formula strings, not query IDs
- **Result registry** — `tests/registry.py`, `tests/test_registry.py`, `docs/testing.md`
- **`q_` prefix dropped** from query IDs
- **`res_analyse` YAML key** confirmed as multi-point evaluation syntax

---

## Known Bugs

### `but`-for vacuity in single-agent moments

When only one agent acts at a moment, `[γ']¬φ` is vacuously true (the PDL box is a material
conditional; at the current index `do(γ')` is false so the whole thing is true). The
counterfactual never actually checks the alternative outcome. Affects `but` and `sres` (which
uses `but` internally) at any moment where fewer agents act than exist in the model.

Fix: evaluate the counterfactual across same-moment indices where γ' is actually performed,
rather than as a material conditional at the current index.

### Auto-generated histories show q and ~q — RESOLVED

Was in the old flat `ALOModel.complete()` / `build_model()`, which have been deleted.
