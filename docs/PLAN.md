# ALOn Toolkit — Open Issues & Roadmap

This document consolidates all known open issues, design decisions pending implementation,
and planned refactors. Update it as work is completed or priorities shift.

Last updated: 2026-06-11

---

## Execution Order

The priorities above describe *what* to build. The order to actually do the work:

1. **Git tag current state** as `pre-cleanup` — cheap insurance before anything is removed
2. **Migrate tests** (subset of Priority 4) — move `alon_experiments/tests/` into streamlit-app
   and confirm baselines pass. This is the safety net everything else depends on.
3. **Generate feature matrix** — table of which features are exercised by existing models/theories,
   to show gaps before assembling the model library. Can be done without user input.
4. **Assemble targeted model library** (Priority 3 of Remaining Features) — *requires user input*:
   which logical properties to demonstrate, expected results, naming. Feature matrix drives this.
5. **Codebase cleanup** (Priority 3) — now safe because tests + models catch regressions
6. **Compiler pipeline** (Priority 1) — model library exercises all the checks being implemented

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
   - *Note: complex (non-literal) proposition labels are not model-level errors. Two planned
     extensions support them: (a) per-moment available actions, (b) TBox-like axioms with
     global effect. TBox axioms will likely be OWL-only. Compatibility is surfaced via
     serialiser tagging, not as issues on the model itself (see 3d below).*
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
     serialisers support them. These are not *issues* per se, just *issues for a given serialiser*.
   - OWL: warn if any leaf lacks `¬∃succ.⊤` assertion (open-world successor problem)
   - OWL: note if TBox-style axioms present (supported)
   - Datalog: flag if any moment label is non-literal (unsupported)
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

## Priority 3 — Codebase Cleanup

### 3a. Remove TD=1 special pathway — DONE

Eliminated. Everything goes through the ALOModel / layered pipeline.

### 3b. Remove TOML support — DONE

TOML was the original model format, superseded by Mermaid+YAML. No model-input TOML parsing
remains. (reasoner_config.toml for binary paths is separate infrastructure, not model input.)

### 3c. Remove debug print statements — DONE

`owl_index_new_expander.py` deleted entirely as part of serializer consolidation.

### 3d. Datalog serializer: reject complex moment propositions cleanly

Checking belongs in semantic analysis (Priority 1), not in the serialiser. The serialiser should
be able to assume it won't be called with incompatible input. In the interim, it should fail fast
with a clear message rather than silently misbehaving.

---

## Priority 4 — Repo Consolidation

**Status:** Agreed strategy, not executed.

- Primary repo: `alon-streamlit-app` (at `/Users/mbassbp2/Development/alon-streamlit-app`)
- Legacy: `deontickit/alon_experiments/alo_translator/` — 35+ commits ahead of origin,
  ~40 debug scripts, all the latest core fixes applied here (not there)

### Steps

1. Commit pending changes in `alon-streamlit-app` (Modeller.py URL param fix, depth2_example.mmd)
2. Diff deontickit core files vs streamlit-app — identify any substantive changes not yet migrated
3. Migrate `alon_experiments/tests/` (test_datalog_baselines.py, test_konclude_baselines.py,
   fixtures/konclude_baselines.json) into streamlit-app
4. Leave behind the 40 debug/experiment scripts (no value)
5. Rename streamlit-app repo to `alon-toolkit` or similar

---

## Priority 5 — Computational Experiment Pipeline Refresh

**Status:** Exists in `deontickit/alon_experiments/`, needs migration and modernisation.

The experiment pipeline (`evaluate_model.py`, `generate_report.py`, `analyze_model.py`) was
used to produce the baseline results in the AAAI supplement. It is currently:
- Entangled with deontickit's older codebase
- Full of manual debug scripts left over from development
- Not cleanly separated from the Streamlit app

### What's needed
- Clean migration to `alon-streamlit-app` (after Priority 4)
- A proper experiment runner that can: (a) run all theories, (b) compare OWL vs Datalog results,
  (c) produce a results table in one command
- Regression tests against Konclude baselines (`tests/fixtures/konclude_baselines.json`)

---

## Known Bugs

### Auto-generated histories show q and ~q — RESOLVED

Was in the old flat `ALOModel.complete()` / `build_model()`, which have been deleted.

---

## Recently Completed (this session)

- Group opposing support end-to-end: parser, OWL serializer, Datalog serializer, display layer
- `free_do` group semantics corrected to Def 3.7 (group freedom independent of individual freedom)
- `res_analyse` vs `evaluate` key distinction implemented at parser, runner, and UI levels
- PyYAML replacing strictyaml (handles flow sequences, special-char keys)
- Non-monotonicity example model (`theories/nonmonotone.mmd`) demonstrating failure of
  antecedent strengthening for `[+]->` (with proof that Sobel sequences are impossible under
  monotonicity of opposing)
- OWL serializers handle complex moment propositions via `_prop_str_to_owl_elem`
- Layered OWL index: removed is_leaf restriction (intermediate moments can have props too)

## Remaining Features

1. Final expressivity: per moment available actions and global/tbox axioms
2. Support functions: E.g., make it easier to generate a model skeleton, implement ridge naming scheme for moments.
3. Refresh IDE.
4. Finish model library.
5. Random generation?