"""
ALOn model builder (Pass 2, 3, 4).

This module converts TOML dictionaries into ALOModel objects and provides
the full pipeline for parsing and expanding queries.

Pipeline:
- Pass 1 (toml_parser.py): Load TOML → Dict
- Pass 2 (this module): Dict → ALOModel (semantic analysis)
- Pass 3 (this module): Parse query strings → FormulaNode AST
- Pass 4 (this module): Expand defined forms → primitive operators

Usage:
    from alo_translator.parsers.toml_parser import load_toml
    from alo_translator.parsers.builder import parse_toml

    # Full pipeline in one call:
    model = parse_toml("path/to/theory.toml")

    # Or step by step:
    toml_dict = load_toml("path/to/theory.toml")
    model = build_model(toml_dict)
    model = parse_queries(model)
"""

from typing import Dict, List, Any, Optional, Union

from ..model.core import (
    ALOModel,
    Action,
    GroupAction,
    OpposingRelation,
    Result,
    Query,
)
from ..query_generation import ResponsibilityConfig
from .formula_parser import parse_formula
from .formula_expander import expand_formula
from .formula_registry import FormulaRegistry
from .hierarchical_expander import HierarchicalExpander


# ============================================================================
# Pass 2: Build ALOModel from TOML dict (semantic analysis)
# ============================================================================

def build_model(toml_dict: Dict[str, Any]) -> ALOModel:
    """
    Build ALOModel from TOML dictionary (Pass 2).

    Performs semantic analysis:
    - Validates required sections
    - Normalizes agent/action identifiers to strings
    - Parses action strings (e.g., "sd1" → Action("sd", "1"))
    - Stores query strings (unparsed)

    Args:
        toml_dict: Dictionary from toml_parser.load_toml()

    Returns:
        ALOModel with all sections populated except query ASTs

    Raises:
        ValueError: If required sections missing or malformed

    Example:
        >>> toml_dict = load_toml("theory.toml")
        >>> model = build_model(toml_dict)
        >>> model.queries[0].formula_string
        'Xq'
        >>> model.queries[0].formula_ast  # None until Pass 3
        None
    """
    # Parse Actions section (required)
    if "Actions" not in toml_dict:
        raise ValueError("TOML file must contain [Actions] section")

    actions_dict = toml_dict["Actions"]
    # Convert all keys to strings for consistency
    agents_actions = {
        str(agent): action_types
        for agent, action_types in actions_dict.items()
    }

    # Parse optional sections
    aliases = _parse_aliases(toml_dict.get("Aliases", {}))
    agent_groups = _parse_agent_groups(toml_dict.get("AgentGroups", {}))
    opposings = _parse_opposings(toml_dict.get("Opposings", {}))
    named_histories = _parse_histories(toml_dict.get("Histories", {}))
    results = _parse_results(toml_dict.get("Results", {}))
    queries = _parse_queries(toml_dict.get("Queries", {}))
    responsibility_config = _parse_responsibility_config(
        toml_dict.get("responsibility_analysis")
    )

    return ALOModel(
        agents_actions=agents_actions,
        aliases=aliases,
        agent_groups=agent_groups,
        opposings=opposings,
        named_histories=named_histories,
        results=results,
        queries=queries,
        responsibility_config=responsibility_config,
    )


# ============================================================================
# Pass 3: Parse query strings to FormulaNode AST
# ============================================================================

def parse_queries(model: ALOModel) -> ALOModel:
    """
    Parse all query strings to FormulaNode AST (Pass 3).

    Updates model.queries[i].formula_ast for each query.
    If responsibility_config is present, generates responsibility queries first.

    Args:
        model: ALOModel with query strings

    Returns:
        Same model with formula_ast populated

    Raises:
        lark.exceptions.LarkError: If any query is malformed

    Example:
        >>> model = build_model(toml_dict)
        >>> model = parse_queries(model)
        >>> model.queries[0].formula_ast
        Next(formula=Prop(symbol='q'))
    """
    # Generate responsibility queries if config is present
    if model.responsibility_config is not None:
        from ..query_generation import generate_queries as gen_resp_queries
        model.queries.extend(gen_resp_queries(model))

    # Parse all query strings to AST
    for query in model.queries:
        if query.formula_ast is None:  # Don't re-parse
            query.formula_ast = parse_formula(query.formula_string)
    return model


# ============================================================================
# Pass 4: Expand defined forms to primitives
# ============================================================================

def expand_queries(model: ALOModel, expand_standard: bool = False,
                   evaluation_history: str = "h1") -> ALOModel:
    """
    Expand all defined forms in queries (Pass 4) using HierarchicalExpander.

    Creates a FormulaRegistry and uses HierarchicalExpander to:
    1. Register each query formula
    2. Expand all formulas breadth-first
    3. Insert NamedFormula references for subformulas
    4. Store the registry in model.formula_registry

    Args:
        model: ALOModel with parsed queries
        expand_standard: If True, also expand standard operators
        evaluation_history: Which history to evaluate on (default "h1")

    Returns:
        Same model with expanded_ast populated and formula_registry attached
    """
    # Create registry and expander
    registry = FormulaRegistry()
    expander = HierarchicalExpander(model, registry)

    # Register all query formulas and track their OWL names
    query_owl_names = {}  # Map query_id -> owl_name

    for query in model.queries:
        if query.formula_ast is None:
            raise ValueError(
                f"Cannot expand query '{query.formula_string}': "
                f"not yet parsed (call parse_queries first)"
            )

        # Register the query formula (adds to pending queue)
        # This returns the OWL name from formula.to_owl_name()
        owl_name = registry.register(query.formula_ast, label=query.formula_string)

        # Track the mapping from query_id to registry key
        if query.query_id:
            query_owl_names[query.query_id] = owl_name
        else:
            # If no query_id, use the OWL name as query_id
            query.query_id = owl_name

    # Expand all formulas breadth-first
    expander.expand_all()

    # Attach registry to model so serializer can use it
    model.formula_registry = registry

    # Set expanded_ast for backward compatibility
    for query in model.queries:
        if query.formula_ast:
            # Look up the OWL name for this query
            owl_name = query_owl_names.get(query.query_id) or query.formula_ast.to_owl_name()
            if owl_name in registry.formulas:
                query.expanded_ast = registry.formulas[owl_name]

    return model


# ============================================================================
# Convenience function: Full pipeline
# ============================================================================

def parse_toml(file_path: str) -> ALOModel:
    """
    Full pipeline: TOML file → ALOModel with parsed queries.

    Runs all passes:
    1. Load TOML → dict
    2. Build model (semantic analysis)
    3. Parse queries (string → AST)

    Args:
        file_path: Path to TOML file

    Returns:
        Complete ALOModel ready for serialization
    """
    from .toml_parser import load_toml

    toml_dict = load_toml(file_path)
    model = build_model(toml_dict)
    model = parse_queries(model)
    return model


# ============================================================================
# Helper functions for parsing TOML sections
# ============================================================================

def _parse_aliases(aliases_dict: Dict[str, str]) -> Dict[str, str]:
    """Parse [Aliases] section - all keys and values converted to strings."""
    return {str(k): str(v) for k, v in aliases_dict.items()}


def _parse_agent_groups(groups_dict: Dict[str, List]) -> Dict[str, List[str]]:
    """
    Parse [AgentGroups] section.

    Format: Ag = [1, 3] means agent group "Ag" consists of agents "1" and "3"

    Returns dictionary mapping group names to lists of agent IDs.
    """
    agent_groups = {}
    for name, agents in groups_dict.items():
        if not isinstance(agents, list):
            raise ValueError(
                f"Agent group '{name}' must be an array, got {type(agents)}"
            )
        # Convert all agent IDs to strings
        agent_groups[name] = [str(agent) for agent in agents]
    return agent_groups


def _parse_opposings(opposings_dict: Dict[str, List[str]]) -> List[OpposingRelation]:
    """
    Parse [Opposings] section.

    Format: sd1 = ["ha2"] means "sd1 is opposed by ha2"

    Returns list of OpposingRelation objects.
    """
    opposings = []
    for opposed_str, opposing_list in opposings_dict.items():
        opposed_action = _parse_action_string(opposed_str)

        for opposing_str in opposing_list:
            opposing_action = _parse_action_string(opposing_str)
            opposings.append(OpposingRelation(opposed_action, opposing_action))

    return opposings


def _parse_histories(histories_dict: Dict[str, Dict[str, str]]) -> Dict[str, GroupAction]:
    """
    Parse [Histories] section.

    Format: h1 = {1 = "sd", 2 = "ss"}

    Returns dictionary mapping history names to GroupAction objects.
    """
    named_histories = {}
    for name, actions_map in histories_dict.items():
        # Convert all keys to strings
        actions = {
            str(agent): action_type
            for agent, action_type in actions_map.items()
        }
        named_histories[name] = GroupAction(actions)

    return named_histories


def _parse_results(results_dict: Dict[str, any]) -> List[Result]:
    """
    Parse [Results] section.

    Format: h1 = ["q"] means proposition "q" is true at the successor of h1
           or h1 = {"moment": "m1", "props": ["q"]} from DBT parser

    Returns list of Result objects.
    """
    results = []
    for history_name, value in results_dict.items():
        # Handle both old format (list) and new format (dict with moment)
        if isinstance(value, dict):
            true_props = set(value.get("props", []))
            moment_name = value.get("moment")
        else:
            true_props = set(value)
            moment_name = None

        results.append(Result(history_name, true_props, moment_name))

    return results


def _parse_queries(queries_dict: Dict[str, List[str]]) -> List[Query]:
    """
    Parse [Queries] section.

    Format: "Effects" = ['Xq', '~[]Xq']

    Returns list of Query objects with category labels.
    """
    queries = []
    for category, query_list in queries_dict.items():
        for query_formula in query_list:
            queries.append(
                Query(formula_string=query_formula, category=category)
            )

    return queries


def _parse_action_string(action_str: str) -> Action:
    """
    Parse an action string like "sd1" into Action object.

    Assumes format: action_type + agent_id
    Examples: "sd1" → Action("sd", "1")
              "ha2" → Action("ha", "2")

    This is a simple heuristic: find where digits start from the end.
    """
    # Find where the agent number starts (from the end)
    i = len(action_str) - 1
    while i >= 0 and action_str[i].isdigit():
        i -= 1

    if i == len(action_str) - 1:
        # No digits found - treat whole string as action type with no agent
        raise ValueError(f"Action string '{action_str}' has no agent number")

    action_type = action_str[:i+1]
    agent = action_str[i+1:]

    return Action(action_type, agent)


def _parse_responsibility_config(
    config_dict: Optional[Dict[str, Any]]
) -> Optional[ResponsibilityConfig]:
    """
    Parse [responsibility_analysis] section.

    Format:
        [responsibility_analysis]
        target_proposition = "q"
        agents = "all"  # or ["1", "3"]
        groups = "all"  # or "singletons" | "size<=2" | [["1", "3"], ["2"]]
        responsibility_types = ["pres", "sres", "res", "dsxtit", "but", "ness"]
        history = "h1"  # optional, defaults to "h1"

    Returns:
        ResponsibilityConfig object or None if section not present
    """
    if config_dict is None:
        return None

    # Required fields
    if "target_proposition" not in config_dict:
        raise ValueError("[responsibility_analysis] must have 'target_proposition'")
    if "responsibility_types" not in config_dict:
        raise ValueError("[responsibility_analysis] must have 'responsibility_types'")

    # Parse agents (can be "all" or a list)
    agents = config_dict.get("agents", "all")
    if isinstance(agents, list):
        agents = [str(a) for a in agents]

    # Parse groups (can be "all", "singletons", "size<=k", or explicit list)
    groups = config_dict.get("groups", "all")
    if isinstance(groups, list) and len(groups) > 0 and isinstance(groups[0], list):
        # Explicit list of coalitions: [[1, 3], [2]]
        groups = [[str(a) for a in coalition] for coalition in groups]

    return ResponsibilityConfig(
        target_proposition=config_dict["target_proposition"],
        agents=agents,
        groups=groups,
        responsibility_types=config_dict["responsibility_types"],
        history=config_dict.get("history", "h1"),
    )
