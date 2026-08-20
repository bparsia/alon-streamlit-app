"""
YAML frontmatter parsing helper for Mermaid diagrams.

Converts YAML frontmatter to partial_spec dict format matching TOML structure.
"""

import yaml
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
        return yaml.safe_load(yaml_string)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML frontmatter: {e}")


def yaml_to_partial_spec(yaml_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert YAML frontmatter data to partial_spec dict format.

    The partial_spec format matches TOML structure:
    - opposings: {action: [opposing_actions]}
    - aliases: {id: "name"}
    - res_analyse: [(moment/history, target_proposition), ...]
    - evaluate: [(moment/history, formula), ...]

    Args:
        yaml_data: Parsed YAML dictionary from frontmatter

    Returns:
        Partial spec dictionary matching TOML structure
    """
    partial_spec = {}

    # Extract opposings
    # YAML format: opposings: {"sd1": ["ha2"]}
    if "opposings" in yaml_data:
        partial_spec["opposings"] = yaml_data["opposings"]

    # Extract aliases
    # YAML format: aliases: {1: "Alice", "sd": "shoots Dan"}
    if "aliases" in yaml_data:
        partial_spec["aliases"] = yaml_data["aliases"]

    # Extract multi-point evaluations (TD>1)
    # YAML format:
    #   res_analyse:
    #     - [m/h1, do(sd1)]
    #     - [mm/h1, q]
    if "res_analyse" in yaml_data:
        partial_spec["res_analyse"] = yaml_data["res_analyse"]

    # Extract direct formula evaluations (no responsibility query generation)
    # YAML format:
    #   evaluate:
    #     - [m/h1, "[]do(sd1)"]
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
