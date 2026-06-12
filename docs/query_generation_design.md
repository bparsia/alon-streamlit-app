# Query Generation Design Issues

Last updated: 2026-06-12

## Current state

`generate_queries()` in `query_generation.py` only handles `ALOModel` (flat TD=1).
`setup_layered_queries()` in `utils.py` handles `LayeredALOModel` but is scoped to a
single `(evaluation_moment, evaluation_history)` pair baked into the model at call time.

Both will need to converge into a single unified path once `ALOModel` is removed.

---

## Design issues to resolve before removing ALOModel

### 1. Evaluation point selection

Three modes are needed:

- **Single designated point** — `(model.evaluation_moment, model.evaluation_history)`,
  the traditional TD=1 behaviour. Simplest, cheapest.
- **All evaluable points** — every non-leaf moment × each history passing through it.
  "Free" when available actions are uniform across moments; can blow up otherwise.
- **Explicit list** — `model.evaluations: list[(moment, history, prop)]` as currently
  implemented. User-specified subset.

### 2. Query deduplication across moments

If two moments share identical available action sets and outcome patterns, they produce
identical queries. We only need one query set for both, but need to track which moments
map to it.

Naively generating one query set per moment wastes computation and clutters output.
Need a deduplication step: group moments by `(frozenset(available_actions), outcome_pattern)`
and generate one `QuerySet` per group.

### 3. Coalition selection knob

Full power set is O(2^n) and expensive. Useful options:

- All singletons only
- Singletons + grand coalition
- All subsets up to size k
- Explicit list of coalitions

This should be a parameter on `ResponsibilityConfig` (currently `groups` field supports
`"all"`, `"singletons"`, `"size<=k"`, explicit list — already partially there).

### 4. But/ness scaling

But/ness queries look up the specific action each agent performed in the designated
history at the evaluation moment. For a model with branching factor b at a moment,
there are b possible histories through that moment, so b possible but/ness query sets.

If evaluating at all points, the number of but/ness queries can be large. The coalition
knob helps (but/ness are naturally singleton queries).

### 5. Output structure

Currently `generate_queries()` returns a flat `list[Query]`. With multiple evaluation
points and deduplication, the output needs more structure:

```python
@dataclass
class QuerySet:
    eval_points: list[tuple[str, str]]  # (moment, history) pairs this set applies to
    queries: list[Query]
```

This allows:
- Serializers to evaluate each `QuerySet` against the right moments (they already do
  this — the structure is informational / for output grouping)
- Results tables to group by evaluation point
- Future: splitting into multiple files per evaluation point if needed

### 6. Unified API

After removing `ALOModel`, the API should be something like:

```python
generate_queries(
    model: LayeredALOModel,
    mode: Literal["designated", "all", "explicit"] = "designated",
    coalitions: str | list = "all",   # reuses ResponsibilityConfig.groups semantics
) -> list[QuerySet]
```

`model.responsibility_config` continues to carry `target_proposition`, `responsibility_types`,
and the explicit evaluation list when `mode="explicit"`.

---

## What to do now (before full redesign)

To unblock the agreement tests and gold standard capture:

- Update `generate_queries` to handle `LayeredALOModel` in "designated single point"
  mode using `model.evaluation_moment` / `model.evaluation_history`.
- Use `model.get_all_agents()` instead of `model.agents_actions.keys()`.
- Use `model.histories[h].complete_actions()` instead of `model.named_histories[h].actions`.
- Keep `ALOModel` path working unchanged.
- Mark both sites with `# TODO: remove ALOModel branch` comments for clean removal later.
