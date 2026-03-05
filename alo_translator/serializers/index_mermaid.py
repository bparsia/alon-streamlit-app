"""
Index Mermaid diagram serializer.

Serializes ALOnModel to Index format with explicit moment pairs.
Each history gets a choice moment and an outcome moment.
"""

from typing import Dict, Any, Optional
from ..model.core import ALOModel, Result


def serialize_index(
    model: ALOModel,
    partial_spec: Optional[Dict[str, Any]] = None,
    mode: str = "complete"
) -> str:
    """
    Serialize ALOnModel to Index Mermaid format with explicit moment pairs.

    Each history is represented as:
    - Choice moment (m_hi): shows actions performed
    - Outcome moment (mi_hi): shows propositions true
    - Succession link between them

    Args:
        model: ALOnModel with histories and results
        partial_spec: Optional partial specification dict (for mode="partial")
        mode: "complete" (all histories) or "partial" (only user-authored)

    Returns:
        Index Mermaid diagram string with YAML frontmatter

    Example:
        >>> mermaid = serialize_index(model, partial_spec, mode="complete")
        >>> print(mermaid)
        ---
        type: Indexed
        ...
        ---
        classDiagram
        direction BT
          class m_h1 {
            sd1()
            ss2()
          }
          class m1_h1 {
            q
          }
          m_h1 --> m1_h1 : succ
    """
    lines = []

    # Generate YAML frontmatter
    if partial_spec:
        lines.append("---")
        lines.append("type: Indexed")

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

    # Generate moment pairs for each history
    for hist_name in sorted(histories_to_output):
        if hist_name not in model.named_histories:
            continue

        group_action = model.named_histories[hist_name]
        result = _find_result(hist_name, model.results)

        # Choice moment: m_h1
        choice_index = f"m_{hist_name}"
        lines.append(f"  class {choice_index} {{")

        # Add actions as methods
        for agent, action_type in sorted(group_action.actions.items()):
            lines.append(f"    {action_type}{agent}()")

        lines.append("  }")

        # Outcome moment: use moment_name from result if available, else default to m1
        moment_name = result.moment_name if result and result.moment_name else "m1"
        outcome_index = f"{moment_name}_{hist_name}"
        lines.append(f"  class {outcome_index} {{")

        # Add propositions as attributes
        if result:
            for prop in sorted(result.true_propositions):
                lines.append(f"    {prop}")

        lines.append("  }")

        # Link choice to outcome
        lines.append(f"  {choice_index} --> {outcome_index} : succ")

    return "\n".join(lines)


def _find_result(history_name: str, results: list) -> Optional[Result]:
    """Find the Result for a given history name."""
    for result in results:
        if result.history_name == history_name:
            return result
    return None
