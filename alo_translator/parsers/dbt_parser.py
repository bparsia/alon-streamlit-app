"""
DBT Mermaid diagram parser.

Parses DBT (Deontic Branching Time) Mermaid diagrams into ALOModel.
"""

import re
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List
from lark import Lark

from ..model.core import (
    Action, OpposingRelation,
    MomentNode, MomentTransition, HistoryPath, ALOModel,
)
from .mermaid_transformer import MermaidTransformer
from .yaml_helper import frontmatter_to_partial_spec


# Load Mermaid grammar using path relative to this file (cwd-independent)
_GRAMMAR_PATH = Path(__file__).parent / "mermaid_class.lark"
with open(_GRAMMAR_PATH) as f:
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
def _parse_action_string(action_str: str) -> Action:
    """Parse 'sd1' -> Action('sd', '1')."""
    m = re.match(r'([a-zA-Z]+)(\d+)', action_str.strip())
    if not m:
        raise ValueError(f"Cannot parse action string: {action_str}")
    return Action(m.group(1), m.group(2))


def _parse_action_or_group(action_str: str):
    """Parse an individual action string 'sd1' or group '{sd1,ha2}'."""
    action_str = action_str.strip()
    if action_str.startswith('{') and action_str.endswith('}'):
        inner = action_str[1:-1]
        actions = {}
        for part in inner.split(','):
            a = _parse_action_string(part.strip())
            actions[a.agent] = a.action_type
        from ..model.core import GroupAction
        return GroupAction(actions)
    return _parse_action_string(action_str)


def _build_layered_opposings(partial_spec: Dict[str, Any]) -> List[OpposingRelation]:
    """Build OpposingRelation list from partial_spec opposings dict."""
    opposings = []
    for opposed_str, opposing_list in partial_spec.get("opposings", {}).items():
        opposed = _parse_action_or_group(opposed_str)
        for opp_str in opposing_list:
            opposings.append(OpposingRelation(opposed, _parse_action_or_group(opp_str)))
    return opposings


def _parse_layered(diagram: Dict[str, Any], partial_spec: Dict[str, Any]) -> 'ALOModel':
    """Build a ALOModel from a TD>1 diagram."""
    succs = diagram.get("succs", [])
    moment_props = diagram.get("moment_props", [])

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
    # 6. Collect propositions from moment_props declarations
    # ------------------------------------------------------------------
    for decl in moment_props:
        moment_name = decl["moment_id"]
        if moment_name not in moment_nodes:
            raise ValueError(f"Proposition label on unknown moment: {moment_name}")
        node = moment_nodes[moment_name]
        for label in decl["propositions"]:
            if default_result is None or label != default_result:
                node.propositions.add(label)

    # ------------------------------------------------------------------
    # 7. Assemble ALOModel
    # ------------------------------------------------------------------
    eval_point = partial_spec.get("evaluation_point", f"m/{sorted(all_history_names)[0]}")
    if "/" in eval_point:
        eval_moment, eval_history = eval_point.rsplit("/", 1)
    else:
        eval_moment = root_name
        eval_history = eval_point

    # Parse multi-point evaluations: [[moment/history, target], ...]
    evaluations = []
    for item in partial_spec.get("res_analyse", []):
        if len(item) >= 2:
            ep, tgt = str(item[0]), str(item[1])
            if "/" in ep:
                emom, ehist = ep.rsplit("/", 1)
            else:
                emom, ehist = root_name, ep
            evaluations.append((emom, ehist, tgt))

    return ALOModel(
        root_name=root_name,
        moments=moment_nodes,
        transitions=transitions,
        histories=histories,
        opposings=_build_layered_opposings(partial_spec),
        aliases={str(k): v for k, v in partial_spec.get("aliases", {}).items()},
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

def parse_dbt_diagram(mermaid_string: str) -> ALOModel:
    """
    Parse a DBT Mermaid diagram into a ALOModel.
    """
    tree = MERMAID_PARSER.parse(mermaid_string)
    transformer = MermaidTransformer()
    parsed = transformer.transform(tree)

    frontmatter_str = parsed.get("frontmatter")
    diagram = parsed.get("diagram")

    if not diagram:
        raise ValueError("No diagram found in Mermaid input")

    partial_spec = frontmatter_to_partial_spec(frontmatter_str)
    return _parse_layered(diagram, partial_spec)
