# Scalability model generator for ALOn `.mmd` models — design doc

Status: draft, not yet implemented. Edit freely.

## Context

Konclude's realization cost on 3.5 (16 histories) is already 33.6s vs 0.6s on
3.1 (4 histories) — a real cliff, not yet characterized as a curve. There is
currently no way to generate models at controlled sizes; every `.mmd` file
(3.1, 3.5, 3.5_3agent, isabella, etc.) is hand-authored, including its `q`
truth-value assignment and (for isabella) its `res_analyse` eval-point list.
`3.5_3agent.mmd` was a one-off manual reduction built earlier this session to
get an "intermediate" data point — this generator replaces that manual
process with a parameterized one so we can build a real size-vs-cost curve
(pyDatalog / OWL-realization / SPARQL-MINUS) and empirically test the
standing intuition: **for a fixed branching factor, going deeper (more
temporal stages) should scale roughly linearly in total-responsibility-query
cost, while widening (more agents/histories at a single stage) scales
combinatorially** — modulo the effect of raw agent count on `ness`'s
powerset search (`expander_transformer.py`'s `ness()` enumerates the
powerset of the acting CGA, so per-query cost is itself exponential in
*agents active at that one eval point*, separate from total history count).

The three axes requested — history/branching width, temporal depth, and
eval-point count — are not independent in the existing format (eval points
are entirely manual `res_analyse` entries), so the generator must also
synthesize eval points, not just diagram structure.

## Design

New module: `alo_translator/model_generation/scalability.py` (new package,
since this is model-authoring logic distinct from parsing/serializing/
reasoning — it produces `.mmd` text, not an analysis result).

### Core parameterization

```python
@dataclass
class ScalabilitySpec:
    agents_per_stage: int       # branching factor: agents acting at each stage
    actions_per_agent: int = 2  # action-vocabulary size per agent (default binary: sd/ss-style)
    depth: int = 1              # number of sequential stages (temporal depth)
    reuse_agents: bool = True   # depth>1 only: same `agents_per_stage` agents act at every stage
                                 # (vs. depth adding NEW agents each stage, which is a width increase in disguise)
    seed: int = 0               # deterministic RNG seed for q-truth assignment
```

This directly matches the framing from the conversation that motivated this
doc: "same size (#nodes) vs max branch vs some sensible small branching
factor," with depth and width as orthogonal knobs, and `reuse_agents` making
explicit the width/depth conflation risk that was flagged ("we might have
fewer agents... where as for flat models we *can* fix the agents by merely
increasing the actions... that's a third dimension really").

### Structure generation

- **Width** (`agents_per_stage`, `actions_per_agent`): at each stage, every
  agent gets `actions_per_agent` action-type choices (named systematically,
  e.g. `a0`, `a1`, ... — avoiding hand-picked names like `sd`/`ss` since
  there's no natural-language scenario). Total histories through one stage
  = `actions_per_agent ** agents_per_stage`. This reuses exactly the
  edge-label mechanism seen in `3.1.mmd`/`3.5.mmd` (`m --> mN :
  hK({a0_1, a1_2, ...})`), just with generated action/agent names instead of
  scenario-specific ones (`sd1`, `ha2`).
- **Depth** (`depth > 1`): chain stages the same way `isabella.mmd` does —
  each non-leaf moment gets its own outgoing edge set, all histories passing
  through a shared prefix stage get grouped on one edge label per the
  `h1/h2({...})` co-labeling syntax `dbt_parser.py:32`'s `parse_dbt_label`
  already handles. With `reuse_agents=True`, the same agent numbers/action
  vocabulary act at every stage (this is what makes "depth at fixed
  branching" a clean, isolated variable — no width is smuggled in via new
  agents per stage).
- **No `opposings`** by default (opposing-action semantics are a scenario
  detail, not a size variable) — omit the frontmatter key entirely, matching
  `3.7.mmd`'s precedent of opposings being fully optional.
- **`q` truth-value assignment**: rather than hand-deriving a semantically
  meaningful rule per size (as was done for `3.5_3agent.mmd`), assign truth
  values in a value-agnostic, deterministic way — `q` true at leaf moment
  `i` iff `hash((seed, i)) % 2 == 0`, or equivalently a seeded
  `random.Random(seed).choice([True, False])` per leaf, walked in a fixed
  (sorted history-name) order for reproducibility. This is intentionally
  arbitrary: the generator's purpose is stress-testing reasoner/compiler
  performance as a function of *structure size*, not modeling a coherent
  scenario, so there is no "correct" derivation to preserve — flag this
  explicitly in the module docstring so it's not mistaken for a semantically
  meaningful model later.

### Eval-point synthesis

Since `res_analyse` is 100% manual today, the generator needs an explicit,
separate policy, exposed as its own parameter rather than folded silently
into structure generation:

```python
    eval_point_mode: Literal["single_root", "all_actual", "fixed_count"] = "single_root"
    eval_point_count: Optional[int] = None  # only used for "fixed_count"
```

- `"single_root"`: one eval point at `m/h1` (matches 3.1/3.5's pattern —
  keeps eval-point count constant across the whole size sweep, isolating
  model-size effects from query-count effects).
- `"all_actual"`: every non-leaf `(moment, history)` pair gets an eval point
  (matches isabella's exhaustive style) — use this specifically for the
  "vary eval-point count at fixed structure" sub-experiment.
- `"fixed_count"`: deterministically sample `eval_point_count` non-leaf
  `(moment, history)` pairs (sorted, then seeded shuffle-and-take) — for
  isolating eval-point-count as its own axis independent of both structure
  size and the "all of them" extreme.

Target proposition for every eval point defaults to `q` (matching every
existing model) — no parameter needed unless a future need arises.

### Output

`generate_scalability_model(spec: ScalabilitySpec) -> str` returns the
`.mmd` text directly (frontmatter + classDiagram), following the exact
syntax confirmed against `3.1.mmd`/`isabella.mmd`:
- `aliases` frontmatter: purely descriptive (agent numbers → `"Agent 0"`
  etc.), safe to omit entirely since aliases are documentation-only
  (`yaml_helper.py` confirms aliases don't affect model semantics) —
  omitting keeps generated files minimal; include only if useful for
  reading generated output during debugging.
- A `title`/`description` frontmatter pair auto-filled with the spec
  parameters (e.g. `"generated: agents=3 actions=2 depth=2
  reuse_agents=True seed=0"`) so a generated file is self-documenting
  without hand-editing.
- No caller-facing file-writing inside this function — return the string;
  a thin caller (test or script) does `Path(...).write_text(...)` if a file
  is wanted. Most uses (the sweep runner below) will parse the string
  directly via `parse_dbt_diagram()` without ever touching disk.

### Sweep runner (reuses `generate_tables.py`'s metric extraction directly)

New script: `tools/scalability_sweep.py` (dev/analysis tool, not
paper-output generation — kept out of `papers/2026Fear/` for that reason,
though trivial to move later if it turns out to be paper-specific).

For each `ScalabilitySpec` in a parameter sweep (e.g. fixed
`agents_per_stage=2`, `depth` in `1..4`; separately, fixed `depth=1`,
`agents_per_stage` in `1..4`):
1. `generate_scalability_model(spec)` → mmd text → `parse_dbt_diagram(text)`
   → `ALOModel`.
2. Reuse `generate_tables.py`'s `model_shape_stats(model)`,
   `max_possible_eval_points(model)` directly (import them — they're
   pure functions of `ALOModel`, no refactor needed) for the structural
   columns.
3. Reuse the same three timing loops `generate_tables.py::run_model()`
   already has (pyDatalog / OWL-realization / SPARQL-MINUS via
   `KoncludeSparqlServer`, using `compile_query_to_sparql` from
   `streamlit_app/utils.py`) — for models past a size cutoff, only run
   SPARQL (skip OWL-realization once it's clearly off the curve, to avoid
   the same >10min stalls that motivated `KONCLUDE_TIMEOUT` in the existing
   script) — expose a `--skip-realization-above N` CLI flag rather than a
   hardcoded cutoff.
4. Emit a CSV (not LaTeX — this is an exploratory sweep, not a paper table)
   with one row per spec: all `ScalabilitySpec` fields, all
   `model_shape_stats` fields, and the three timing columns. CSV over LaTeX
   because the whole point is to plot/inspect a curve, not typeset a fixed
   table; can add a LaTeX/plot export later once the shape of the data is
   known.

### What this design deliberately does NOT do

- Does not touch `ness`'s powerset-search cost itself (see the MSC section
  below — a separate, later piece of work).
- Does not attempt to auto-derive a "meaningful" `q` truth rule at scale;
  explicitly documented as arbitrary/seeded.
- Does not add generated models to `PAPER_MODELS` in
  `papers/2026Fear/generate_tables.py` — that list stays hand-curated to the
  scenario-meaningful models (3.1/3.5/3.6/3.7/isabella); the sweep is a
  separate script/output.
- Does not implement the "one shared SPARQL server per model" question left
  open from the isabella methodology discussion — out of scope here, can
  revisit once the sweep's own SPARQL timing loop exists (it will hit the
  same per-eval-point-server-restart question at larger eval-point counts,
  making it a natural point to reopen that question empirically rather than
  in the abstract).

## MSC (minimum sufficient cause) as a first-class operator — scoped follow-up, not designed here

Confirmed via exploration: MSC is already fully specified formally in
`papers/2026Fear/paper_mirror/2Prelims.tex` (`msCause`/`\msC`, lines
189-190) as `[a]φ ∧ ⋀_{K⊊agents(a)} ¬[proj(a,K)]φ`, and the paper explicitly
proves NESS is equivalent to "sub-action of some MSC" and argues MSC is the
conceptually simpler notion the codebase should prefer.
`ExpanderTransformer.ness()`
(`alo_translator/parsers/expander_transformer.py:378-492`) already computes
the exact powerset/minimality search MSC needs internally, but only keeps
the OR'd-together final result — it never surfaces *which* `J` were the
minimal sufficient sets, which is what a first-class `msc(a, φ)` /
`msc_set(φ)` operator would need to expose.

This is a real, separable piece of work (new grammar rule, new transformer
method mirroring `ness()`'s search but returning per-`J` witnesses rather
than one OR'd axiom, serializer guards, docs). It is not designed here —
this needs its own design pass once the scalability tester is done.

## Files to create

- `alo_translator/model_generation/__init__.py` (new package)
- `alo_translator/model_generation/scalability.py` — `ScalabilitySpec`,
  `generate_scalability_model()`
- `tests/unit/test_scalability_generation.py` — parse-round-trip tests
  (generated mmd parses via `parse_dbt_diagram`, history count matches
  `actions_per_agent ** agents_per_stage` per stage, depth matches spec,
  eval-point count matches mode, determinism given fixed seed)
- `tools/scalability_sweep.py` — sweep runner + CSV writer, reusing
  `generate_tables.py`'s stat functions and `utils.py`'s
  `compile_query_to_sparql`

## Verification plan

1. Unit tests: generate small specs (`agents_per_stage=2, depth=1`),
   confirm `parse_dbt_diagram` succeeds and `model_shape_stats` reports the
   expected history/moment/depth counts; generate `depth=2` and confirm
   `max_possible_eval_points` matches the two-stage tree shape (same check
   `isabella.mmd` satisfies today).
2. Run `tools/scalability_sweep.py` for a small width sweep
   (`agents_per_stage` 1→3, `depth=1`, `actions_per_agent=2`,
   `eval_point_mode=single_root`) and a small depth sweep (`depth` 1→3,
   `agents_per_stage=2`) with `--skip-realization-above` set low enough to
   finish in reasonable time; inspect the CSV to confirm the width sweep
   shows the expected combinatorial growth and the depth sweep shows
   roughly linear growth in per-query time, consistent with (or correcting)
   the standing intuition — per CLAUDE.md, report the measured numbers
   without hypothesizing about *why* before running this.
