"""
DBT Mermaid diagram parser.

Parses DBT (Deontic Branching Time) Mermaid diagrams into ALOn models.

For TD=1 diagrams returns (ALOModel, partial_spec) to enable round-tripping.
For TD>1 diagrams (intermediate moments detected) returns LayeredALOModel.
"""

import re
from typing import Dict, Any, Tuple, Optional, List
from lark import Lark

from ..model.core import (
    ALOModel, Result, Action, OpposingRelation,
    MomentNode, MomentTransition, HistoryPath, LayeredALOModel,
)
from .mermaid_transformer import MermaidTransformer
from .yaml_helper import frontmatter_to_partial_spec
from .builder import build_model


# Load Mermaid grammar
with open("alo_translator/parsers/mermaid_class.lark", "r") as f:
    MERMAID_GRAMMAR = f.read()

MERMAID_PARSER = Lark(MERMAID_GRAMMAR, start="start", parser="lalr")


# ---------------------------------------------------------------------------
# Label parsing
# ---------------------------------------------------------------------------

def parse_dbt_label(label: str) -> Tuple[List[str], Dict[str, str]]:
    """
    Parse a DBT transition label to extract history names and stage actions.

    Format: "h1({sd1, ss2})" or "h1/h2({masd3})"

    Args:
        label: Transition label from diagram

    Returns:
        Tuple of (history_names, actions_dict)
        - history_names: All history names on this edge (e.g. ["h1", "h2"])
        - actions_dict: {agent_id: action_type} for agents acting at this stage

    Examples:
        >>> parse_dbt_label("h1({sd1, ss2})")
        (["h1"], {"1": "sd", "2": "ss"})

        >>> parse_dbt_label("h1/h2({masd3})")
        (["h1", "h2"], {"3": "masd"})
    """
    # Extract slash-separated history names before the opening paren
    history_match = re.match(r'([\w/-]+)\s*\(', label)
    if not history_match:
        raise ValueError(f"Invalid DBT label format: {label}")

    history_names = [h.strip() for h in history_match.group(1).split("/")]

    # Extract actions from braces: {sd1, ss2}
    actions_match = re.search(r'\{([^}]+)\}', label)
    if not actions_match:
        raise ValueError(f"No actions found in DBT label: {label}")

    actions_str = actions_match.group(1)

    # Parse individual actions: "sd1, ss2" -> {"1": "sd", "2": "ss"}
    actions_dict: Dict[str, str] = {}
    for action_str in actions_str.split(","):
        action_str = action_str.strip()
        action_match = re.match(r'([a-zA-Z]+)(\d+)', action_str)
        if not action_match:
            raise ValueError(f"Invalid action format: {action_str}")
        action_type = action_match.group(1)
        agent_id = action_match.group(2)      # keep as str
        actions_dict[agent_id] = action_type

    return history_names, actions_dict


# ---------------------------------------------------------------------------
# TD=1 path (preserved)
# ---------------------------------------------------------------------------

def extract_histories_and_results(diagram: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, str]], Dict[str, dict]]:
    """
    Extract histories and results from a TD=1 parsed Mermaid diagram.

    Histories come from succession transitions (succs).
    Results come from shorthand member declarations.
    """
    histories = {}
    results = {}

    # Accumulate propositions per outcome moment
    outcome_props: Dict[str, List[str]] = {}
    for shorthand in diagram.get("shorthand_members", []):
        moment_id = shorthand["identifier"]
        value = shorthand["value"]
        props = [p.strip() for p in value.split(",")]
        if moment_id not in outcome_props:
            outcome_props[moment_id] = []
        outcome_props[moment_id].extend(props)

    # Extract histories from transitions
    for succ in diagram.get("succs", []):
        label = succ.get("label")
        if not label:
            continue

        history_names, actions_dict = parse_dbt_label(label)
        history_name = history_names[0]        # TD=1: one history per edge
        histories[history_name] = actions_dict

        outcome_moment = succ["to_moment"]
        props = outcome_props.get(outcome_moment, [])
        results[history_name] = {"moment": outcome_moment, "props": props}

    return histories, results


def _parse_flat(diagram: Dict[str, Any], partial_spec: Dict[str, Any]) -> Tuple[ALOModel, Dict[str, Any]]:
    """Build a TD=1 (ALOModel, partial_spec) pair — the existing pipeline."""
    diagram_histories, diagram_results = extract_histories_and_results(diagram)

    if "histories" not in partial_spec:
        partial_spec["histories"] = {}
    partial_spec["histories"].update(diagram_histories)

    if "results" not in partial_spec:
        partial_spec["results"] = {}
    partial_spec["results"].update(diagram_results)

    if "actions" not in partial_spec:
        raise ValueError("DBT diagram must specify actions in frontmatter")

    toml_dict = {"Actions": partial_spec["actions"]}
    if "opposings" in partial_spec:
        toml_dict["Opposings"] = partial_spec["opposings"]
    if "aliases" in partial_spec:
        toml_dict["Aliases"] = partial_spec["aliases"]
    if "histories" in partial_spec:
        toml_dict["Histories"] = partial_spec["histories"]
    if "results" in partial_spec:
        toml_dict["Results"] = partial_spec["results"]

    model = build_model(toml_dict)

    target_prop = partial_spec.get("result", "q")
    eval_point = partial_spec.get("evaluation_point", "m/h1")
    eval_history = eval_point.split("/")[-1] if "/" in eval_point else eval_point
    model.complete(target_prop, eval_history)

    return model, partial_spec


# ---------------------------------------------------------------------------
# TD>1 path
# ---------------------------------------------------------------------------

def _is_layered(diagram: Dict[str, Any]) -> bool:
    """Return True if the diagram has intermediate moments (TD>1)."""
    succs = diagram.get("succs", [])
    to_moments = {s["to_moment"] for s in succs}
    from_moments = {s["from_moment"] for s in succs}
    # A moment that appears as both source and target is an intermediate node
    return bool(to_moments & from_moments)


def _parse_action_string(action_str: str) -> Action:
    """Parse 'sd1' -> Action('sd', '1')."""
    m = re.match(r'([a-zA-Z]+)(\d+)', action_str.strip())
    if not m:
        raise ValueError(f"Cannot parse action string: {action_str}")
    return Action(m.group(1), m.group(2))


def _build_layered_opposings(partial_spec: Dict[str, Any]) -> List[OpposingRelation]:
    """Build OpposingRelation list from partial_spec opposings dict."""
    opposings = []
    for opposed_str, opposing_list in partial_spec.get("opposings", {}).items():
        opposed = _parse_action_string(opposed_str)
        for opp_str in opposing_list:
            opposings.append(OpposingRelation(opposed, _parse_action_string(opp_str)))
    return opposings


def _parse_layered(diagram: Dict[str, Any], partial_spec: Dict[str, Any]) -> 'LayeredALOModel':
    """Build a LayeredALOModel from a TD>1 diagram."""
    succs = diagram.get("succs", [])
    shorthand_members = diagram.get("shorthand_members", [])

    default_result = partial_spec.get("defaults", {}).get("result") if partial_spec.get("defaults") else None

    # ------------------------------------------------------------------
    # 1. Build directed graph and enumerate all moments
    # ------------------------------------------------------------------
    outgoing: Dict[str, List[str]] = {}
    incoming: Dict[str, List[str]] = {}
    all_moment_names: set = set()

    for succ in succs:
        fm, tm = succ["from_moment"], succ["to_moment"]
        outgoing.setdefault(fm, []).append(tm)
        incoming.setdefault(tm, []).append(fm)
        all_moment_names.update([fm, tm])

    # ------------------------------------------------------------------
    # 2. Find root (no incoming edges)
    # ------------------------------------------------------------------
    roots = [m for m in all_moment_names if m not in incoming]
    if len(roots) != 1:
        raise ValueError(f"Expected exactly one root moment, found: {roots}")
    root_name = roots[0]

    # ------------------------------------------------------------------
    # 3. BFS to assign depths and build MomentNode skeletons
    # ------------------------------------------------------------------
    moment_nodes: Dict[str, MomentNode] = {}
    queue = [(root_name, None, 0)]
    while queue:
        name, parent, depth = queue.pop(0)
        children = outgoing.get(name, [])
        moment_nodes[name] = MomentNode(
            name=name,
            parent_name=parent,
            child_names=list(children),
            available_actions={},
            propositions=set(),
            depth=depth,
        )
        for child in children:
            queue.append((child, name, depth + 1))

    # ------------------------------------------------------------------
    # 4. Parse edges → MomentTransitions, accumulate available_actions
    # ------------------------------------------------------------------
    transitions: List[MomentTransition] = []
    for succ in succs:
        fm, tm = succ["from_moment"], succ["to_moment"]
        label = succ.get("label")
        if not label:
            raise ValueError(f"Every edge in a TD>1 diagram must have a label ({fm} --> {tm} has none)")

        history_names, actions = parse_dbt_label(label)

        transitions.append(MomentTransition(
            from_moment=fm,
            to_moment=tm,
            histories=history_names,
            actions=actions,
        ))

        # Accumulate available actions on the from-moment
        node = moment_nodes[fm]
        for agent, action_type in actions.items():
            node.available_actions.setdefault(agent, [])
            if action_type not in node.available_actions[agent]:
                node.available_actions[agent].append(action_type)

    # ------------------------------------------------------------------
    # 5. Build HistoryPaths
    # ------------------------------------------------------------------
    all_history_names: set = set()
    for t in transitions:
        all_history_names.update(t.histories)

    histories: Dict[str, HistoryPath] = {}
    for hist_name in sorted(all_history_names):
        # Collect transitions for this history, ordered by from-moment depth
        hist_trans = sorted(
            [t for t in transitions if hist_name in t.histories],
            key=lambda t: moment_nodes[t.from_moment].depth,
        )
        if not hist_trans:
            raise ValueError(f"History {hist_name} has no transitions")

        path = [hist_trans[0].from_moment] + [t.to_moment for t in hist_trans]
        actions_at = {t.from_moment: t.actions for t in hist_trans}

        histories[hist_name] = HistoryPath(
            name=hist_name,
            path=path,
            actions_at=actions_at,
        )

    # ------------------------------------------------------------------
    # 6. Collect propositions from shorthand_members
    # ------------------------------------------------------------------
    for shorthand in shorthand_members:
        moment_name = shorthand["identifier"]
        if moment_name not in moment_nodes:
            raise ValueError(f"Proposition label on unknown moment: {moment_name}")
        node = moment_nodes[moment_name]
        for label in (p.strip() for p in shorthand["value"].split(",")):
            if default_result is None or label != default_result:
                node.propositions.add(label)

    # ------------------------------------------------------------------
    # 7. Assemble LayeredALOModel
    # ------------------------------------------------------------------
    eval_point = partial_spec.get("evaluation_point", f"m/{sorted(all_history_names)[0]}")
    if "/" in eval_point:
        eval_moment, eval_history = eval_point.rsplit("/", 1)
    else:
        eval_moment = root_name
        eval_history = eval_point

    # Parse multi-point evaluations: [[moment/history, target], ...]
    evaluations = []
    for item in partial_spec.get("evaluate", []):
        if len(item) >= 2:
            ep, tgt = str(item[0]), str(item[1])
            if "/" in ep:
                emom, ehist = ep.rsplit("/", 1)
            else:
                emom, ehist = root_name, ep
            evaluations.append((emom, ehist, tgt))

    return LayeredALOModel(
        root_name=root_name,
        moments=moment_nodes,
        transitions=transitions,
        histories=histories,
        opposings=_build_layered_opposings(partial_spec),
        aliases=partial_spec.get("aliases", {}),
        queries=[],
        evaluation_history=eval_history,
        evaluation_moment=eval_moment,
        target_proposition=partial_spec.get("result", "q"),
        default_result=default_result,
        evaluations=evaluations,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_dbt_diagram(mermaid_string: str):
    """
    Parse a DBT Mermaid diagram into an ALOn model.

    For TD=1 diagrams returns (ALOModel, partial_spec).
    For TD>1 diagrams returns LayeredALOModel.
    """
    tree = MERMAID_PARSER.parse(mermaid_string)
    transformer = MermaidTransformer()
    parsed = transformer.transform(tree)

    frontmatter_str = parsed.get("frontmatter")
    diagram = parsed.get("diagram")

    if not diagram:
        raise ValueError("No diagram found in Mermaid input")

    partial_spec = frontmatter_to_partial_spec(frontmatter_str)

    if _is_layered(diagram):
        return _parse_layered(diagram, partial_spec)
    else:
        return _parse_flat(diagram, partial_spec)
