"""
YAML frontmatter parsing helper for Mermaid diagrams.

Converts YAML frontmatter to partial_spec dict format matching TOML structure.
"""

from strictyaml import load, YAMLError
from typing import Dict, Any, Optional


def parse_yaml_frontmatter(yaml_string: str) -> Dict[str, Any]:
    """
    Parse YAML frontmatter string into a structured dict.

    Args:
        yaml_string: Raw YAML content from frontmatter

    Returns:
        Parsed YAML as a dictionary

    Raises:
        ValueError: If YAML parsing fails
    """
    try:
        parsed = load(yaml_string)
        return parsed.data
    except YAMLError as e:
        raise ValueError(f"Failed to parse YAML frontmatter: {e}")


def yaml_to_partial_spec(yaml_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert YAML frontmatter data to partial_spec dict format.

    The partial_spec format matches TOML structure:
    - actions: {agent_id: [action_list]}
    - opposings: {action: [opposing_actions]}
    - aliases: {id: "name"}
    - histories: {history_name: {agent: action}}
    - results: {history_name: [props]}
    - result: str (singular, for queries)
    - evaluation_point: str (e.g., "m/h1")
    - diagram_type: str ("DBT" or "Indexed")

    Args:
        yaml_data: Parsed YAML dictionary from frontmatter

    Returns:
        Partial spec dictionary matching TOML structure
    """
    partial_spec = {}

    # Extract diagram type (not part of TOML, but metadata)
    if "type" in yaml_data:
        partial_spec["diagram_type"] = yaml_data["type"]

    # Extract actions (required for building model)
    # YAML format: actions: {1: ["sd", "ss"], 2: ["ss", "ha"]}
    if "actions" in yaml_data:
        # Convert agent IDs to integers if they're strings
        actions = {}
        for agent, action_list in yaml_data["actions"].items():
            agent_id = int(agent) if isinstance(agent, str) and agent.isdigit() else agent
            actions[agent_id] = action_list
        partial_spec["actions"] = actions

    # Extract opposings
    # YAML format: opposings: {"sd1": ["ha2"]}
    if "opposings" in yaml_data:
        partial_spec["opposings"] = yaml_data["opposings"]

    # Extract aliases
    # YAML format: aliases: {1: "Alice", "sd": "shoots Dan"}
    if "aliases" in yaml_data:
        partial_spec["aliases"] = yaml_data["aliases"]

    # Extract histories (if specified in frontmatter)
    # YAML format: histories: {"h1": {1: "sd", 2: "ss"}}
    if "histories" in yaml_data:
        histories = {}
        for hist_name, hist_actions in yaml_data["histories"].items():
            # Convert agent IDs to integers if they're strings
            converted_hist = {}
            for agent, action in hist_actions.items():
                agent_id = int(agent) if isinstance(agent, str) and agent.isdigit() else agent
                converted_hist[agent_id] = action
            histories[hist_name] = converted_hist
        partial_spec["histories"] = histories

    # Extract results (if specified in frontmatter)
    # YAML format: results: {"h1": ["q"]}
    if "results" in yaml_data:
        partial_spec["results"] = yaml_data["results"]

    # Extract single result for queries (singular!)
    # YAML format: result: "q"
    if "result" in yaml_data:
        partial_spec["result"] = yaml_data["result"]

    # Extract outcome proposition (takes precedence over result if both present)
    # YAML format: outcome: "do(sd1)"
    if "outcome" in yaml_data:
        partial_spec["result"] = yaml_data["outcome"]

    # Extract evaluation point for queries
    # YAML format: evaluation_point: "m/h1"
    if "evaluation_point" in yaml_data:
        partial_spec["evaluation_point"] = yaml_data["evaluation_point"]

    # Extract defaults block (TD>1)
    # YAML format:
    #   defaults:
    #     result: ~q
    if "defaults" in yaml_data:
        partial_spec["defaults"] = yaml_data["defaults"]

    # Extract multi-point evaluations (TD>1)
    # YAML format:
    #   evaluate:
    #     - [m/h1, do(sd1)]
    #     - [mm/h1, q]
    if "evaluate" in yaml_data:
        partial_spec["evaluate"] = yaml_data["evaluate"]

    return partial_spec


def frontmatter_to_partial_spec(frontmatter_string: Optional[str]) -> Dict[str, Any]:
    """
    Parse YAML frontmatter string and convert to partial_spec format.

    This is the main entry point that combines parsing and conversion.

    Args:
        frontmatter_string: Raw YAML frontmatter string (or None if no frontmatter)

    Returns:
        Partial spec dictionary, or empty dict if no frontmatter

    Raises:
        ValueError: If YAML parsing fails
    """
    if frontmatter_string is None or not frontmatter_string.strip():
        return {}

    yaml_data = parse_yaml_frontmatter(frontmatter_string)
    return yaml_to_partial_spec(yaml_data)
