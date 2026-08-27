# HermiT (via ROBOT) reasoner backend + DL-safe-rule OWL post-processor

**STATUS 2026-08-27: CLOSED — route set aside by the user ("the sparql/dlsafe route is dead at the moment"). Final state, not superseded further:**
- `HermitAdapter` (via ROBOT): done, working, verified against the known-good baseline.
- DL-safe-rules post-processor (`dlsafe_rules.py`): correctness bug found and fixed — callers must exclude `outcome_*` query IDs from the rule-conversion set (root cause unknown, workaround verified end-to-end, full 14/14 match at 3.1-scale).
- 3.5-scale (16 histories, 91 queries) performance: structural bottleneck fixed (switching to the existing `EquivChainedNominalStrategy` gives 1.1s vs 300s+ timeout for the bare model), but a SECOND, separate query-axiom-related bottleneck remains unresolved — confirmed present even in a single agent's minimal 38-axiom dependency closure, in both plain-axiom and full-DL-safe-rules form. Never found a minimal reproducing case smaller than that.
- Usable as-is for 3.1/3.6/3.7/isabella-scale models; NOT usable for 3.5-scale until/unless the second bottleneck is understood.
- See `docs/reasoner_oddities.md` for full experimental trail. Five candidate future directions (Konclude SPARQL fix, Konclude nominal-schema support, HermiT's alleged SPARQL/BGP support, HermiT internals optimization, a new DBox-based reasoner) recorded there and in memory but none started.

## Context

SPARQL-on-Konclude (prior thread) was abandoned — see `alon-streamlit-app/docs/sparql_serializer_ABANDONED.md` — because Konclude's SPARQL negation is broken and the responsibility operators depend on negation too pervasively to work around. Redirected to DL-safe rules via HermiT instead: real rule-based OWL reasoning, not a SPARQL workaround, and a second independent reasoner backend alongside Konclude.

Two pieces, both confirmed working via direct testing against real current-code `.owl` output (3.1.mmd's `m/h1/q` eval point) — not toy examples, not assumed:

1. **HermiT has no CLI for "which named individuals satisfy which classes"** (only classification/consistency, confirmed via `--help`). **ROBOT** (a CLI wrapper around the OWL API, already present at `/Users/mbassbp2/Development/deontickit/alon_experiments/reasonerstuff/robot/robot`) solves this as a plain subprocess call, with output already matching this codebase's OWL/XML format.
2. **`SubClassOf` query-definition axioms translate mechanically into `DLSafeRule`s** — same complex expression, moved from the axiom's LHS into a rule body atom, with a bare class as the rule head. No negation-as-failure needed: DL-safe rule atoms accept arbitrary OWL class expressions including `ObjectComplementOf`, which is real classical negation baked into the expression itself — this is *why* the rule-based approach works where SPARQL's negation-as-failure mechanisms didn't.

## Confirmed working, end to end

```
robot reason -r HermiT -i <in.owl> -n true -A ClassAssertion -d true \
      convert --format owx -o <out.owx>
```
(ROBOT supports command chaining — `convert` implicitly takes `reason`'s output, one subprocess call, no intermediate file.) Ran against 3.1.mmd's real `m/h1/q` OWL file: produced all 14 expected query classes for `m_h1` (`pres_1_q_m_h1_q`, `sres_1_q_m_h1_q`, `res_1_q_m_h1_q`, `but_sd1_q_m_h1_q`, `ness_sd1_q_m_h1_q`, `but_ss2_q_m_h1_q`, `ness_ss2_q_m_h1_q`, `pres_1_2_q_m_h1_q`, `sres_1_2_q_m_h1_q`, `res_1_2_q_m_h1_q`, `dxstit_1_2_q_m_h1_q`, `but_1_2_q_m_h1_q`, `ness_1_2_q_m_h1_q`, `outcome_m_h1_q`), exact match to the already-verified pyDatalog/Konclude result. Output is real OWL/XML (`<Declaration>`/`<ClassAssertion>` shapes), directly parseable the same way `KoncludeAdapter.parse_output` already parses Konclude's output.

Two flags matter and are easy to get wrong: `-A ClassAssertion` (without it, `reason` only materializes class-subsumption axioms, no individual types at all) and `-d true` (without it, only *direct* types are materialized — the query classes sit two derivation-hops away from each individual, so only the intermediate `f`-numbered formula classes show up, not the final named query classes).

DL-safe rule translation confirmed on a real extracted axiom (`f20`, a `box`-containing formula `[](do({sd1,ha2}) -> Xq)`, pulled from the real file with its full ABox intact — hand-built toy ABoxes produced spurious failures earlier, traced to missing `ObjectExactCardinality` domain-closure axioms that the real serializer always includes; extracting from a real file sidesteps that class of error entirely): `SubClassOf(<complex expr>, f20)` → `DLSafeRule(Body(ClassAtom(<same complex expr>, Variable(:x))) Head(ClassAtom(f20_rule, Variable(:x))))` gives identical classification to the original axiom.

**Known scaling limit** (reconfirmed on current code, not just an old archived finding): HermiT/ROBOT handles 3.1's file (19 queries, 94KB) in seconds; 3.5's file (91 queries, 806KB) times out past 300s. Scope this backend as viable for smaller models only (3.1/3.6/3.7/isabella-scale) — 3.5 is a known exclusion, not a bug to fix here.

## Design

### 1. `HermitAdapter` — new file `alo_translator/reasoners/hermit.py`

Mirrors `KoncludeAdapter` (`alo_translator/reasoners/konclude.py`):
- `supports_mode()`: `REALISATION` only.
- `run(ontology_file, mode, timeout=None)`: single subprocess call, `[robot_path, "reason", "-r", "HermiT", "-i", str(ontology_file), "-n", "true", "-A", "ClassAssertion", "-d", "true", "convert", "--format", "owx", "-o", str(output_path)]`, via `subprocess.run(cmd, timeout=timeout)` — same pattern as `KoncludeAdapter`, genuine subprocess timeout, no in-process JVM management needed.
- `parse_output`: reuse/adapt `KoncludeAdapter.parse_output`'s XML handling — confirm the exact shape matches closely enough to share code before assuming zero changes needed.
- Add a `robot_path()` locator function alongside `konclude_path()` in `streamlit_app/utils.py`. Decide whether to vendor the `robot` executable into `alon-streamlit-app/bin/` (matching how Konclude's binary lives there) rather than pointing at the `deontickit` repo's scratch directory long-term.

### 2. DL-safe-rule post-processor — new file `alo_translator/serializers/dlsafe_rules.py`

Post-processes an already-serialized OWL/XML string/tree (does not touch `FormulaToOWL`/`OWLSerializer` — stays mechanically in sync with whatever they produce, per the user's preferred design: a post-processing pass, not a parallel serializer):
- For each `SubClassOf` whose head is a bare `Class` matching a real query ID (same check `OWLSerializer._add_expansion_axioms` already uses, `alo_translator/serializers/owl.py:650`): rewrite into a `DLSafeRule` — deep-copy the LHS subtree unchanged into a `ClassAtom` + fresh `Variable`, head is `ClassAtom(<same query class>, <same variable>)`.
- Axioms whose head is not a bare query-ID class (the file surveyed had one such case, a totality axiom `SubClassOf(owl:Thing, ObjectSomeValuesFrom(succ, owl:Thing))`) pass through unchanged — confirm there's nothing else in this category before assuming it's just the one shape.
- Use a generic tree-transplant (`copy.deepcopy` the LHS `Element`), not manual per-shape reconstruction — the real file has 56 query-definition axioms with varied nesting; hand-rebuilding each would be error-prone.

### 3. Wire into the analysis pipeline

New function in `streamlit_app/utils.py`, `run_analysis_hermit_layered`, mirroring `run_analysis_konclude_layered`: build the OWL ontology as today, run it through the DL-safe-rule post-processor, then `HermitAdapter`, read `individual_types` the same way. Given the scaling limit, the caller (or this function itself) should warn/refuse above some query-count threshold — determine the real threshold by testing isabella's and 3.6/3.7's actual per-eval-point query counts, not by assuming from the single 19-works/91-fails datapoint.

## Verification

- Diff the post-processor's generated `DLSafeRule` for a real axiom against the hand-built `f20_rule` from this session's manual test — must match structurally.
- Run the full query set for 3.1.mmd's `m/h1/q` through the complete pipeline (post-processor → `HermitAdapter`) and confirm it matches the already-verified pyDatalog/Konclude results exactly.
- Test isabella's and 3.6/3.7's real per-eval-point query counts through the same pipeline to establish the actual scaling threshold.
- Confirm there are no `SubClassOf` head shapes besides "bare query-ID class" and "the one totality axiom" before assuming the post-processor's pass-through case is complete.
- Do not speculate about *why* HermiT's scaling cliff exists — per the standing no-reasoner-hypothesizing rule (`CLAUDE.md`, `feedback_no_reasoner_hypothesizing` memory), applies to HermiT exactly as much as Konclude.
