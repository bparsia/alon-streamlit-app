# ALOn Toolkit — Open Issues & Roadmap

This document consolidates all known open issues, design decisions pending implementation,
and planned refactors. Update it as work is completed or priorities shift.

Last updated: 2026-06-13

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

### 3a. Per-moment available actions

Currently every agent has the same action set at every moment. The model should support
specifying different available actions per moment (e.g. agent 1 can only do `sd` at `m` but
`sd` or `ha` at `m1`). Impacts: parser, `MomentNode`, semantic analysis (CGA coverage check),
both serialisers.

### 3b. TBox-style global axioms

Axioms with global effect (e.g. `do(sd1) → Xq`) that apply across all indices rather than
being asserted at a specific moment. These are likely OWL-only (Datalog would need NAF-safe
rewriting). Semantic analysis tags models containing TBox axioms as OWL-only.

---

## Priority 4 — Model Library

Two distinct purposes requiring different model designs:

### 4a. Test models
Minimal models that exercise specific features and have known ground-truth results (verified
against Konclude baselines). Drive regression testing and serialiser compatibility checks.
Feature matrix (which features each existing model exercises) should be generated first to
identify gaps.

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

## Priority 6 — Services (All Points)

**Status:** Not started.

The app currently evaluates at a single (moment, history) pair. "All points" means running
the analysis at every valid evaluation index and aggregating results — showing which
responsibility claims hold globally vs locally.

Also includes exposing the pipeline as a REST/JSON service for programmatic access.

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

---

## Known Bugs

### Auto-generated histories show q and ~q — RESOLVED

Was in the old flat `ALOModel.complete()` / `build_model()`, which have been deleted.
