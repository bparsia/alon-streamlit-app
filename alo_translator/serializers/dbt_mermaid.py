"""
DBT Mermaid diagram serializer.

Serializes ALOnModel to DBT (Deontic Branching Time) Mermaid format.
Supports both partial and complete output modes.
"""

from typing import Dict, Any, Optional, Set
from ..model.core import ALOModel, Result


def serialize_dbt(
    model: ALOModel,
    partial_spec: Optional[Dict[str, Any]] = None,
    mode: str = "complete"
) -> str:
    """
    Serialize ALOnModel to DBT Mermaid format.

    Args:
        model: ALOnModel with histories and results
        partial_spec: Optional partial specification dict (for mode="partial")
        mode: "complete" (all histories) or "partial" (only user-authored)

    Returns:
        DBT Mermaid diagram string with YAML frontmatter

    Example:
        >>> mermaid = serialize_dbt(model, partial_spec, mode="complete")
        >>> print(mermaid)
        ---
        type: DBT
        actions:
          1:
            - sd
            - ss
        ...
        ---
        classDiagram
        direction BT
          class m {
          }
          m --> m1 : h1({sd1, ss2})
          m1: q
    """
    lines = []

    # Generate YAML frontmatter
    if partial_spec:
        lines.append("---")
        lines.append("type: DBT")

        # Add actions
        if "actions" in partial_spec:
            lines.append("actions:")
            for agent, action_list in sorted(partial_spec["actions"].items()):
                lines.append(f"  {agent}:")
                for action in action_list:
                    lines.append(f"    - {action}")

        # Add opposings if present
        if "opposings" in partial_spec and partial_spec["opposings"]:
            lines.append("opposings:")
            for opposed, opposing_list in sorted(partial_spec["opposings"].items()):
                lines.append(f"  {opposed}:")
                for opposing in opposing_list:
                    lines.append(f"    - {opposing}")

        # Add aliases if present
        if "aliases" in partial_spec and partial_spec["aliases"]:
            lines.append("aliases:")
            for key, value in sorted(partial_spec["aliases"].items()):
                lines.append(f"  {key}: {value}")

        # Add result and evaluation_point if present
        if "result" in partial_spec:
            lines.append(f"result: {partial_spec['result']}")

        if "evaluation_point" in partial_spec:
            lines.append(f"evaluation_point: {partial_spec['evaluation_point']}")

        lines.append("---")

    # Determine which histories to output
    if mode == "partial" and partial_spec and "histories" in partial_spec:
        histories_to_output = list(partial_spec["histories"].keys())
    else:
        histories_to_output = list(model.named_histories.keys())

    # Generate diagram
    lines.append("classDiagram")
    lines.append("direction BT")

    # Initial moment (always empty in DBT)
    lines.append("  class m {")
    lines.append("  }")

    # Each history gets its own outcome moment: m1, m2, m3, m4
    # Generate transitions
    for idx, hist_name in enumerate(sorted(histories_to_output), start=1):
        if hist_name not in model.named_histories:
            continue

        group_action = model.named_histories[hist_name]
        outcome_id = f"m{idx}"

        # Format actions: {sd1, ss2}
        actions_str = _format_actions(group_action)
        lines.append(f"  m --> {outcome_id} : {hist_name}({{{actions_str}}})")

    # Generate shorthand propositions for outcome moments
    for idx, hist_name in enumerate(sorted(histories_to_output), start=1):
        if hist_name in model.named_histories:
            result = _find_result(hist_name, model.results)
            props_str = _format_propositions(result.true_propositions) if result else ""
            outcome_id = f"m{idx}"
            lines.append(f"  {outcome_id}: {props_str}")

    return "\n".join(lines)


def _group_by_outcome(model: ALOModel, histories: list) -> Dict[frozenset, str]:
    """
    Group histories by their outcome propositions.

    Assigns moment IDs (m1, m2, ...) to each unique outcome.

    Args:
        model: ALOnModel
        histories: List of history names to include

    Returns:
        Dict mapping proposition sets to moment IDs
    """
    outcome_map = {}
    moment_counter = 1

    for hist_name in histories:
        if hist_name not in model.named_histories:
            continue

        result = _find_result(hist_name, model.results)
        props_key = frozenset(result.true_propositions) if result else frozenset()

        if props_key not in outcome_map:
            outcome_map[props_key] = f"m{moment_counter}"
            moment_counter += 1

    return outcome_map


def _find_result(history_name: str, results: list) -> Optional[Result]:
    """Find the Result for a given history name."""
    for result in results:
        if result.history_name == history_name:
            return result
    return None


def _format_actions(group_action) -> str:
    """
    Format group action as string: "sd1, ss2"

    Args:
        group_action: GroupAction object

    Returns:
        Formatted string of actions
    """
    actions = []
    for agent, action_type in sorted(group_action.actions.items()):
        actions.append(f"{action_type}{agent}")
    return ", ".join(actions)


def _format_propositions(props: Set[str]) -> str:
    """
    Format proposition set as string: "q" or "~q" or "q, ~p"

    Args:
        props: Set of proposition strings (possibly negated)

    Returns:
        Formatted string of propositions
    """
    if not props:
        return ""

    # Sort for deterministic output
    return ", ".join(sorted(props))
