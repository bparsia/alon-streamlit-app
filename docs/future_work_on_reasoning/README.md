# Future work on reasoning

Consolidated home for everything related to the (closed, 2026-08-27) DL-safe-rules-via-HermiT
investigation and the abandoned SPARQL-on-Konclude thread before it, plus the fixtures/scripts
that back specific findings so they don't rot in a session-ephemeral scratchpad.

See `docs/reasoner_oddities.md` (top section) for the closure summary and the five candidate
future directions. See `docs/sparql_serializer_ABANDONED.md` and `docs/owl_rules_investigation.md`
for the earlier SPARQL-specific findings each direction builds on.

## Contents

- `find_breakpoint.py` — the same-moment-neighborhood-size sweep script referenced in
  `reasoner_oddities.md`'s "Found the actual breakover point" entry and in future direction #4
  (optimize HermiT internals). Run against `fixtures/breakpoint_sweep/3_5_bare_directed.owl`-style
  input (regenerate via `EquivChainedNominalStrategy` if that base file isn't present) through
  ROBOT+HermiT to reproduce the n=1..16 timing table.
- `fixtures/breakpoint_sweep/` — the actual generated `.owl` variants for n=1,2,4,6,8,10,12,14,16
  from that sweep (n=12 = 41.1s, n=14/16 = timeout past 120s under clean load).
- `fixtures/agent1_minimal_closure/` — the true BFS-computed transitive-dependency-closure minimal
  reproduction (38 of 312 axioms) for agent 1's queries in 3.5.mmd, in both plain-`SubClassOf`
  (`3_5_agent1_minimal.owl`) and full-`DLSafeRule` (`3_5_agent1_minimal_rules.owl`) form. Both
  still time out at 180s — this is the smallest reproducing case found for the unresolved
  second (query-axiom) 3.5-scale bottleneck.
- `fixtures/3_5_chained_nominal*.owl` — 3.5.mmd's real OWL output via `EquivChainedNominalStrategy`:
  bare structure (`_bare` suffix, 1.1s), full 91-query plain-axiom form, and full DL-safe-rules
  form (both of the latter two still time out past 180s).
- `fixtures/sparql_test*.owl` — the stale-vs-fresh pair from the `ObjectAllValuesFrom`/
  `ObjectSomeValuesFrom` methodological-error episode (see `reasoner_oddities.md`); kept as a
  concrete example of what "consistent code state" means when re-testing, not as a reasoning fixture.

## Not included here

Dozens of other intermediate scratch files from the investigation (bisection steps, one-off
variants) were not copied — they were superseded by the entries above or were purely diagnostic
dead ends. If a specific superseded file is needed, the method to regenerate it is always
documented in `reasoner_oddities.md`; the file itself was not judged worth permanently keeping.
