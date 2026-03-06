"""
DBT Mermaid diagram parser.

Parses DBT (Deontic Branching Time) Mermaid diagrams into ALOnModel.
Returns tuple: (ALOnModel, partial_spec) to enable round-tripping.
"""

import re
from typing import Dict, Any, Tuple, Optional
from lark import Lark

from ..model.core import ALOModel, Result
from .mermaid_transformer import MermaidTransformer
from .yaml_helper import frontmatter_to_partial_spec
from .builder import build_model


# Load Mermaid grammar
with open("alo_translator/parsers/mermaid_class.lark", "r") as f:
    MERMAID_GRAMMAR = f.read()

MERMAID_PARSER = Lark(MERMAID_GRAMMAR, start="start", parser="lalr")


def parse_dbt_label(label: str) -> Tuple[str, Dict[int, str]]:
    """
    Parse a DBT transition label to extract history name and actions.

    Format: "h1({sd1, ss2})" or "h1/h2({iasd3})"

    Args:
        label: Transition label from diagram

    Returns:
        Tuple of (history_name, actions_dict)
        - history_name: First history name (e.g., "h1")
        - actions_dict: {agent_id: action_type} (e.g., {1: "sd", 2: "ss"})

    Examples:
        >>> parse_dbt_label("h1({sd1, ss2})")
        ("h1", {1: "sd", 2: "ss"})

        >>> parse_dbt_label("h1/h2({iasd3})")
        ("h1", {3: "iasd"})
    """
    # Extract history names (before the brace)
    # Format: "h1({...})" or "h1/h2({...})"
    history_match = re.match(r"([a-zA-Z0-9_-]+)(?:/[a-zA-Z0-9_-]+)*\s*\(", label)
    if not history_match:
        raise ValueError(f"Invalid DBT label format: {label}")

    history_name = history_match.group(1)

    # Extract actions from braces: {sd1, ss2}
    actions_match = re.search(r"\{([^}]+)\}", label)
    if not actions_match:
        raise ValueError(f"No actions found in DBT label: {label}")

    actions_str = actions_match.group(1)

    # Parse individual actions: "sd1, ss2" -> {1: "sd", 2: "ss"}
    actions_dict = {}
    for action_str in actions_str.split(","):
        action_str = action_str.strip()
        # Match action format: action_type + agent_id (e.g., "sd1" -> "sd" + "1")
        # Handle multi-character action types (e.g., "iasd3")
        action_match = re.match(r"([a-zA-Z]+)(\d+)", action_str)
        if not action_match:
            raise ValueError(f"Invalid action format: {action_str}")

        action_type = action_match.group(1)
        agent_id = int(action_match.group(2))
        actions_dict[agent_id] = action_type

    return history_name, actions_dict


def extract_histories_and_results(diagram: Dict[str, Any]) -> Tuple[Dict[str, Dict[int, str]], Dict[str, dict]]:
    """
    Extract histories and results from parsed Mermaid diagram.

    Histories come from succession transitions (succs).
    Results come from shorthand member declarations.

    Args:
        diagram: Parsed diagram dict from MermaidTransformer

    Returns:
        Tuple of (histories_dict, results_dict)
        - histories_dict: {history_name: {agent: action}}
        - results_dict: {history_name: {"moment": moment_name, "props": [props]}}
    """
    histories = {}
    results = {}

    # Map outcome moments to propositions
    outcome_props = {}
    for shorthand in diagram.get("shorthand_members", []):
        moment_id = shorthand["identifier"]
        value = shorthand["value"]
        # Parse propositions: "q" or "~q" or "q, ~p"
        props = [p.strip() for p in value.split(",")]
        outcome_props[moment_id] = props

    # Extract histories from transitions
    for succ in diagram.get("succs", []):
        label = succ.get("label")
        if not label:
            continue

        # Parse label to get history name and actions
        history_name, actions_dict = parse_dbt_label(label)
        histories[history_name] = actions_dict

        # Get results for this history's outcome moment
        outcome_moment = succ["to_moment"]
        props = outcome_props.get(outcome_moment, [])
        results[history_name] = {"moment": outcome_moment, "props": props}

    return histories, results


def parse_dbt_diagram(mermaid_string: str) -> Tuple[ALOModel, Dict[str, Any]]:
    """
    Parse a DBT Mermaid diagram into an ALOnModel.

    Returns tuple (model, partial_spec) to enable round-tripping:
    - model: Complete ALOnModel with all generated histories
    - partial_spec: User-authored partial specification (for serialization)

    Args:
        mermaid_string: Full Mermaid diagram string (with frontmatter)

    Returns:
        Tuple of (ALOnModel, partial_spec_dict)

    Raises:
        ValueError: If diagram is malformed or missing required sections

    Example:
        >>> mermaid = '''---
        ... type: DBT
        ... actions:
        ...   1:
        ...     - sd
        ...     - ss
        ...   2:
        ...     - ss
        ...     - ha
        ... ---
        ... classDiagram
        ... direction BT
        ...   class m {
        ...   }
        ...   m --> m1 : h1({sd1, ss2})
        ...   m1: q
        ... '''
        >>> model, partial_spec = parse_dbt_diagram(mermaid)
        >>> len(model.named_histories)
        4
        >>> partial_spec["histories"]
        {"h1": {1: "sd", 2: "ss"}}
    """
    # Parse Mermaid with Lark
    tree = MERMAID_PARSER.parse(mermaid_string)
    transformer = MermaidTransformer()
    parsed = transformer.transform(tree)

    # Extract frontmatter and diagram
    frontmatter_str = parsed.get("frontmatter")
    diagram = parsed.get("diagram")

    if not diagram:
        raise ValueError("No diagram found in Mermaid input")

    # Parse YAML frontmatter to partial_spec
    partial_spec = frontmatter_to_partial_spec(frontmatter_str)

    # Extract histories and results from diagram
    diagram_histories, diagram_results = extract_histories_and_results(diagram)

    # Merge diagram histories/results with frontmatter (diagram takes precedence)
    if "histories" not in partial_spec:
        partial_spec["histories"] = {}
    partial_spec["histories"].update(diagram_histories)

    if "results" not in partial_spec:
        partial_spec["results"] = {}
    partial_spec["results"].update(diagram_results)

    # Verify required fields
    if "actions" not in partial_spec:
        raise ValueError("DBT diagram must specify actions in frontmatter")

    # Build TOML-like dict for builder (capitalized keys)
    toml_dict = {
        "Actions": partial_spec["actions"],
    }

    # Add optional sections (capitalized keys)
    if "opposings" in partial_spec:
        toml_dict["Opposings"] = partial_spec["opposings"]

    if "aliases" in partial_spec:
        toml_dict["Aliases"] = partial_spec["aliases"]

    if "histories" in partial_spec:
        toml_dict["Histories"] = partial_spec["histories"]

    if "results" in partial_spec:
        toml_dict["Results"] = partial_spec["results"]

    # Build complete ALOnModel
    model = build_model(toml_dict)

    # Generate all complete group actions and add them to named_histories
    all_group_actions = model.generate_complete_group_actions()

    # Assign names to ALL histories (opposing relations don't block histories)
    history_counter = 1
    for group_action in all_group_actions:
        # Check if this group action already has a name
        existing_name = None
        for name, existing_ga in model.named_histories.items():
            if existing_ga.actions == group_action.actions:
                existing_name = name
                break

        if existing_name is None:
            # Generate a new name
            while f"h{history_counter}" in model.named_histories:
                history_counter += 1
            new_name = f"h{history_counter}"
            model.named_histories[new_name] = group_action
            history_counter += 1

    # Generate default results for histories not in partial_spec
    existing_result_histories = {r.history_name for r in model.results}
    specified_props = set()
    for result in model.results:
        specified_props.update(result.true_propositions)

    # Find highest moment number from existing results
    moment_counter = 1
    for result in model.results:
        if result.moment_name:
            # Extract number from moment name like "m1", "m2", etc.
            match = re.match(r'm(\d+)', result.moment_name)
            if match:
                moment_num = int(match.group(1))
                moment_counter = max(moment_counter, moment_num + 1)

    # Default: unspecified histories have all specified props negated and new moments
    for hist_name in model.named_histories.keys():
        if hist_name not in existing_result_histories:
            # Default to negation of all specified propositions
            negated_props = {f"~{p}" if not p.startswith("~") else p[1:]
                           for p in specified_props}
            # Assign new moment number
            new_moment = f"m{moment_counter}"
            moment_counter += 1
            model.results.append(Result(hist_name, negated_props, new_moment))

    return model, partial_spec
