# ALOn Temporal Depth-N: Implementation Plan

_Last revised: 2026-04-24_

---

## Design Principles

1. **Mermaid-only.** The TOML format is legacy and will not be extended. It will not be broken (TD=1 TOML diagrams continue to work), but all new development targets the DBT Mermaid format.
2. **Complete diagrams required for TD>1.** Partial specification is deferred. Multistep diagrams must enumerate all transitions explicitly. Available actions are inferred from the diagram rather than declared in YAML.
3. **No breakage of TD=1.** The existing flat `ALOModel` and its serializer pipeline are preserved as-is. The layered pipeline activates when the diagram has intermediate moments (TD>1).
4. **`LayeredALOModel` is the eventual unified model.** For now, the two classes coexist. The goal is that `LayeredALOModel` with TD=1 is behaviorally identical to `ALOModel`, and eventually replaces it.
5. **Default rules for repetition.** A `defaults:` mechanism in frontmatter specifies the default outcome proposition, removing the need to label every leaf and removing the hardcoded `~q` convention.

---

## Key Departures from Standard ALOn

### Variable action availability per moment

In standard ALOn, all agents have all actions available at every moment. In a TD>1 structure, different agents act at different moments. This is necessary for the semantics to be non-trivial: if Alice's `ss1` were available at every moment, `[]do(sd1)` would always be false (since some same-moment index would have Alice doing ss instead of sd). Instead:

- Actions are only available to an agent at the moment where they choose — i.e., where their action label appears on outgoing transitions from that moment.
- Action facts are asserted only at the indices for that moment.
- `[]φ` evaluated at index `(mom, h)` means φ holds at all same-moment indices. The same-moment group at `mom` contains only the histories that actually pass through `mom` — histories that diverged before `mom` have no indices at `mom` and are not in the group.

The expander (which generates TBox rules for responsibility operators like `xstit`, `pres`, etc.) must receive an `evaluation_moment` context so it knows which actions are available when expanding `xstit` and related operators. This is true for all TD — it just happens to be invisible in TD=1 because there is only one moment (the root).

### Undivided histories

`m --> mm : h1/h2({masd3})` means h1 and h2 are *undivided* at m and mm: they share the same tree node and only diverge after mm. Same-moment groups are built per moment-node: all histories that pass through a given node are same-moment there.

**This is new syntax** relative to the current TD=1 DBT format, which uses `m --> m1 : h1({...})` (single history per edge).

### Evaluation is always at the specified index

All responsibility queries are evaluated at the evaluation index (e.g., `m/h1`). This is model checking — the evaluation point is fixed. If `do(sd1)` is not true at the evaluation index (because Alice acts at a later moment), then `but_for(sd1, q)` and related operators are simply false there. If you want to assess Alice's responsibility at the moment she acts, set `evaluation_point: mm/h1`.

---

## Diagram Format

### Transitions

```
m --> mm : h1/h2({masd3})        # h1 and h2 undivided; Isabella does masd
m --> mmm : h3/h4/h5/h6({ss3})  # h3–h6 undivided; Isabella stands still

mm --> m1 : h1({sd1, ss2})       # h1 resolves: Alice shoots, Beth still
mm --> m2 : h2({sd1, ha2})       # h2 resolves: Alice shoots, Beth hits Alice

mmm --> m3 : h3({sd1, ss2})
mmm --> m4 : h4({sd1, ha2})
mmm --> m5 : h5({ss1, ss2})
mmm --> m6 : h6({ss1, ha2})
```

Label format: `h1/h2/...({action1, action2, ...})` — slash-separated history names (all histories undivided on this edge) followed by the actions chosen at this transition (only the agents who choose here).

**Moment naming convention (aspirational):** Terminal moment `mN` corresponding to history `hN` makes the diagram easier to read. Not enforced by the parser, but encouraged.

### Intermediate moment labels

```
mm: do(sd1)        # proposition true at mm for all histories through mm
```

Same emission logic as leaf labels: `do(X)` emits action facts at all `(mm, h)` indices; everything else emits prop facts.

### Outcome (leaf) labels

```
m1: q
m2: ~q
```

Labels are matched against `defaults.result`. A label that matches the default generates no facts — it is the default case and CWA handles the falsity of the non-default proposition. A label that does not match the default generates facts normally.

In the example above with `defaults: result: ~q`:
- `m1: q` — does not match default → assert `prop('m1_h1', 'q')`
- `m2: ~q` — matches default → generate no facts (q is false at m2 by CWA)
- Any unlabeled leaf — matches default → generate no facts

The `~q` convention is not hardcoded. If the model used `defaults: result: q` (positive default), then unlabeled leaves would have q true (via explicit assertion or by different convention), and `~q` labels would generate `prop(leaf, '~q')` facts.

### Frontmatter

```yaml
---
type: DBT
actions:
  1:
    - sd
    - ss
  2:
    - ss
    - ha
  3:
    - ss
    - masd
opposings:
  sd1:
    - ha2
aliases:
  sd: shoots Dan
  ...
result: q
evaluation_point: m/h1
defaults:
  result: ~q
---
```

`actions:` is kept for alias and opposing lookup. Format uses strictyaml block style (no inline lists).

Available actions per moment are inferred from the diagram transitions — no `moment_actions:` key is needed as input. The serializer may output the inferred `moment_actions:` as part of a generated/exported spec.

---

## Default Rules

The `defaults:` block specifies the default outcome proposition:

```yaml
defaults:
  result: ~q    # any leaf whose label matches this string, or any unlabeled leaf, gets no facts
```

The parser applies defaults after collecting explicit labels:
1. For each leaf with an explicit label that does not match `defaults.result`: generate facts
2. For each leaf with an explicit label that matches `defaults.result`: generate no facts
3. For each leaf with no label: generate no facts (same as matching default)

Future extension (deferred): subtree-level defaults to handle deep models with heterogeneous default outcomes.

---

## Data Structures (`core.py`)

New classes alongside existing `ALOModel` (which is untouched):

```python
@dataclass
class MomentNode:
    name: str
    parent_name: Optional[str]                   # None for root
    child_names: List[str]                       # empty for leaves
    available_actions: Dict[str, List[str]]      # agent -> [action_types], inferred from outgoing edges
    propositions: Set[str]                       # props to assert at this moment (non-default only)
    depth: int                                   # 0 for root

    @property
    def is_leaf(self) -> bool:
        return not self.child_names

    @property
    def is_root(self) -> bool:
        return self.parent_name is None


@dataclass
class MomentTransition:
    from_moment: str
    to_moment: str
    histories: List[str]              # all history names undivided on this edge
    actions: Dict[str, str]           # agent -> action_type chosen at this moment


@dataclass
class HistoryPath:
    name: str                                         # "h1", "h2", ...
    path: List[str]                                   # moment names root → leaf: ["m", "mm", "m1"]
    actions_at: Dict[str, Dict[str, str]]             # moment_name -> {agent: action_type}

    @property
    def leaf_moment(self) -> str:
        return self.path[-1]

    def complete_actions(self) -> Dict[str, str]:
        """Merge all per-moment actions (for CGA compatibility)."""
        result = {}
        for acts in self.actions_at.values():
            result.update(acts)
        return result


@dataclass
class LayeredALOModel:
    root_name: str
    moments: Dict[str, MomentNode]         # name -> MomentNode
    transitions: List[MomentTransition]
    histories: Dict[str, HistoryPath]      # name -> HistoryPath
    opposings: List[OpposingRelation]
    aliases: Dict[str, str]
    queries: List[Query]
    evaluation_history: str                # e.g. "h1"
    evaluation_moment: str                 # e.g. "m" (root) or "mm"
    target_proposition: str               # e.g. "q" or "do(sd1)"

    def histories_through(self, moment_name: str) -> List[str]:
        return [h for h, hp in self.histories.items() if moment_name in hp.path]

    def get_all_agents(self) -> Set[str]:
        agents = set()
        for node in self.moments.values():
            agents.update(node.available_actions.keys())
        return agents

    def depth(self) -> int:
        return max(node.depth for node in self.moments.values())

    def available_actions_at(self, moment_name: str) -> Dict[str, List[str]]:
        """Actions available to each agent at the given moment."""
        return self.moments[moment_name].available_actions
```

**Unification goal:** `LayeredALOModel` with `depth() == 1` is behaviourally equivalent to `ALOModel`. Eventually `LayeredALOModel` replaces `ALOModel` entirely and the distinction disappears.

---

## Parser Changes (`dbt_parser.py`)

### `parse_dbt_label()` — updated return type

Currently returns `(first_history_name: str, actions: Dict)`, discarding all but the first history name.

New: `(history_names: List[str], actions: Dict[str, str])`

The grammar (`mermaid_class.lark`) does not need to change — label content is already passed through as a string, and parsing happens in Python.

### `build_moment_tree()` — replaces `extract_histories_and_results()`

1. Collect all edges (`succs`) from the parsed diagram. (`succs` is the key produced by the Mermaid transformer for all `-->` edges in both DBT and index diagrams.)
2. Build a directed graph `{from_moment: [to_moment, ...]}`.
3. Identify root = the node with no incoming edges.
4. BFS from root: assign depths, build `MomentNode` skeletons.
5. For each edge, call updated `parse_dbt_label()` → `(history_names, actions)`. Build a `MomentTransition`. Populate `available_actions` on the from-moment node from the action keys seen on its outgoing edges.
6. For each history name, trace its path through the edge graph from root to leaf → build `HistoryPath`.
7. Collect `shorthand_members` (the `moment: label` declarations):
   - Match each label against `defaults.result` from frontmatter (default: `~q`)
   - Labels matching the default → no facts
   - Labels not matching → add to `MomentNode.propositions`
8. Return `LayeredALOModel`.

### `parse_dbt_diagram()` — dispatch by depth

```python
def parse_dbt_diagram(mermaid_string: str):
    tree = MERMAID_PARSER.parse(mermaid_string)
    parsed = MermaidTransformer().transform(tree)
    diagram = parsed["diagram"]
    partial_spec = frontmatter_to_partial_spec(parsed.get("frontmatter"))

    if _is_layered(diagram):
        return _parse_layered(diagram, partial_spec)  # -> LayeredALOModel
    else:
        return _parse_flat(diagram, partial_spec)     # -> (ALOModel, partial_spec) — existing path
```

`_is_layered()`: True if any moment appears as both a `to_moment` and a `from_moment` (i.e., there is an intermediate node).

Callers in `Modeller.py` and `utils.py` need a type check to route to the appropriate serializer.

---

## Serializer Changes

A new `LayeredDatalogIndexSerializer` handles `LayeredALOModel`. The existing `DatalogIndexSerializer` is unchanged.

### Index generation

One index per `(moment, history)` pair across all moments on each history's path:

```python
for hp in self.model.histories.values():
    for moment_name in hp.path:
        yield (moment_name, hp.name)
```

### Successor facts

One succ edge per consecutive moment pair on each history's path:

```python
for hp in self.model.histories.values():
    for i in range(len(hp.path) - 1):
        from_idx = f"{hp.path[i]}_{hp.name}"
        to_idx   = f"{hp.path[i+1]}_{hp.name}"
        facts.append(f"+ succ('{from_idx}', '{to_idx}')")
```

### Same-moment facts

All histories through a given moment are same-moment at that moment:

```python
for moment_name in self.model.moments:
    histories_here = self.model.histories_through(moment_name)
    idxs = [f"{moment_name}_{h}" for h in sorted(histories_here)]
    # emit reflexive + symmetric chain as in TD=1
```

### Action facts

Actions are asserted only at the index for the moment where the agent chose — not duplicated elsewhere:

```python
for hist_name, hp in self.model.histories.items():
    for moment_name, acts in hp.actions_at.items():
        idx = f"{moment_name}_{hist_name}"
        for agent, action_type in acts.items():
            facts.append(f"+ action('{idx}', '{action_type}{agent}')")
```

(The TD=1 serializer has a hack that asserts action facts at both the root index and the successor index, to support `do(X)` as a target proposition. In the layered model this is unnecessary because `do(X)` facts at intermediate moments are handled via `MomentNode.propositions`.)

### Proposition facts

All facts are per index. For each moment node, emit prop/action facts at every index that moment participates in:

```python
for moment_name, node in self.model.moments.items():
    for prop in node.propositions:               # only non-default props are stored here
        for hist_name in self.model.histories_through(moment_name):
            idx = f"{moment_name}_{hist_name}"
            action_name = _do_prop_action(prop)
            if action_name:
                facts.append(f"+ action('{idx}', '{action_name}')")
            else:
                facts.append(f"+ prop('{idx}', '{prop}')")
```

---

## Expander Changes (`expander_transformer.py` / `PyDatalogExpanderTransformer`)

Responsibility operators (`xstit`, `dxstit`, `pres`, `sres`, `res`, `but_for`, `ness`) enumerate agent actions when generating TBox rules. Currently they read from `model.agents_actions` (a global per-agent action list). For `LayeredALOModel`, actions are per-moment.

The expander only needs to generate rules for the **evaluation moment** — we are doing model checking at a fixed index, not generating rules for all possible moments.

### Change: `evaluation_moment` parameter

Add `evaluation_moment: str` to `PyDatalogExpanderTransformer.__init__()`:

- When present (layered path): `xstit` expansion uses `model.available_actions_at(evaluation_moment)[agent]`
- When absent (TD=1 path): falls back to `model.agents_actions` — no change for existing behaviour

`but_for(sd1, q)` and `ness` continue to work by standard model-checking semantics: if `do(sd1)` is false at the evaluation index, `but_for` is false there. No special logic is needed to "find the moment where the agent chose" — that's the user's responsibility when setting `evaluation_point` in the frontmatter.

`~[]do(α)` (the freedom conjunct in `sres`/`res`) similarly evaluates at the evaluation index using the same available-actions table. No special handling needed beyond the `evaluation_moment` context.

---

## Backward Compatibility

| Component | Status |
|---|---|
| TOML format | **Frozen** — no new features, no changes |
| TD=1 DBT mermaid diagrams | **Unchanged** — `_is_layered()` returns False, existing path runs |
| `ALOModel` dataclass | **Unchanged** |
| `DatalogIndexSerializer` | **Unchanged** |
| `DatalogSerializer` (TBox rules) | **Unchanged** |
| Mermaid grammar (`mermaid_class.lark`) | **Unchanged** |
| Formula grammar (`alon_grammar_clean.lark`) | **Unchanged** |
| `parse_dbt_label()` | **Updated** — returns `List[str]` of history names instead of just the first. This is the only parser-level change that touches existing code; TD=1 diagrams have single-history labels so the first element of the list is equivalent to the old return value. |
| `expander_transformer.py` | **Unchanged for TD=1** — `evaluation_moment` param defaults to None, falling back to existing `agents_actions` lookup |
| `Modeller.py` / `utils.py` | **Type-dispatch shim** — route `LayeredALOModel` to new serializer; `ALOModel` continues on existing path |

---

## Implementation Phases

### Phase 1 — Data structures
Add `MomentNode`, `MomentTransition`, `HistoryPath`, `LayeredALOModel` to `core.py`. No pipeline changes. Unit tests for `histories_through()`, path tracing, `available_actions_at()`.

### Phase 2 — Parser
- Update `parse_dbt_label()` to return all history names
- Implement `build_moment_tree()` in `dbt_parser.py`
- Implement `_is_layered()` and dispatch in `parse_dbt_diagram()`
- Apply `defaults.result` filtering to moment labels

### Phase 3 — Serializer (ABox)
- Implement `LayeredDatalogIndexSerializer`: index generation, succ chains, same-moment grouping, per-moment action facts, proposition facts
- Hook up `evaluate()` using existing pyDatalog exec machinery
- Keep existing `DatalogIndexSerializer` untouched

### Phase 4 — Expander (TBox)
- Add `evaluation_moment` parameter to `PyDatalogExpanderTransformer`
- Update `xstit`/`dxstit`/`pres`/`sres`/`res` to use `model.available_actions_at(evaluation_moment)` when context is set

### Phase 5 — Streamlit
- Type-dispatch in `utils.py` and `Modeller.py`
- Route `LayeredALOModel` to `LayeredDatalogIndexSerializer`
- Evaluation history/moment selection in the UI

### Phase 6 — Testing
- Hand-compute expected results for the Isabella/Alice/Beth TD=2 example
- Verify `Xdo(sd1)`, `XXq`, `[]do(sd1)`, `X[]do(sd1)` at `m/h1` and at `mm/h1`
- Verify pres/sres/res/but/ness for all three agents at both evaluation points

---

## Open Questions / Deferred

1. **Subtree-level defaults**: `defaults: result: ~q` handles a single global default. A more expressive mechanism for heterogeneous defaults (some subtrees have q as default, others ~q) is deferred.
2. **Table-based input format**: Specifying available actions per moment in YAML and generating the transition diagram from a table is an interesting alternative input format, deferred.
3. **Multi-query evaluation across indices**: Evaluating all responsibility queries at every index (not just the evaluation point) would need many more queries and structured output. Deferred.
