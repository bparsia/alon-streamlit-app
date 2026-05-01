"""Shortcode expansion — {{name arg="val" ...}} → rendered markdown."""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional, Tuple

from .document import ALOnDocument, ModelBlock

# Matches {{name}} or {{name key="val" key2="val2"}}
_SHORTCODE_RE = re.compile(r'\{\{(\w+)(?:\s+([^}]*))?\}\}')
_ARG_RE       = re.compile(r'(\w+)="([^"]*)"')


def _parse_args(raw: Optional[str]) -> Dict[str, str]:
    if not raw:
        return {}
    return {m.group(1): m.group(2) for m in _ARG_RE.finditer(raw)}


# ------------------------------------------------------------------
# Individual shortcode renderers
# ------------------------------------------------------------------

def _alias_table(model: ModelBlock) -> str:
    aliases = model.aliases
    if not aliases:
        return "*No aliases defined.*"
    rows = ["| Short | Meaning |", "|-------|---------|"]
    for k in sorted(aliases.keys(), key=lambda x: (x.isdigit(), x)):
        rows.append(f"| `{k}` | {aliases[k]} |")
    return "\n".join(rows)


def _action_table(model: ModelBlock) -> str:
    actions = model.actions
    aliases = model.aliases
    if not actions:
        return "*No actions defined.*"

    rows = ["| Agent | Actions |", "|-------|---------|"]
    for agent_id in sorted(actions.keys(), key=lambda x: (not x.isdigit(), x)):
        action_list = actions[agent_id]
        agent_name  = aliases.get(agent_id, f"Agent {agent_id}")
        action_strs = []
        for a in action_list:
            label = aliases.get(a, a)
            action_strs.append(f"`{a}` ({label})" if label != a else f"`{a}`")
        rows.append(f"| {agent_name} (`{agent_id}`) | {', '.join(action_strs)} |")
    return "\n".join(rows)


def _opposing_table(model: ModelBlock) -> str:
    opposings = model.opposings
    aliases   = model.aliases
    if not opposings:
        return "*No opposings defined.*"

    rows = ["| Action | Opposed by |", "|--------|------------|"]
    for action, opponents in opposings.items():
        opp_strs = [f"`{o}`" for o in opponents]
        rows.append(f"| `{action}` | {', '.join(opp_strs)} |")
    return "\n".join(rows)


def _model_overview(model: ModelBlock) -> str:
    fm      = model.resolved_fm
    aliases = model.aliases
    lines   = []

    if fm.get("title"):
        lines.append(f"**Title**: {fm['title']}")
    if fm.get("description"):
        lines.append(f"**Description**: {fm['description']}")
    if fm.get("type"):
        lines.append(f"**Type**: {fm['type']}")

    # Agents
    actions = model.actions
    if actions:
        agent_parts = []
        for agent_id in sorted(actions.keys(), key=lambda x: (not x.isdigit(), x)):
            name = aliases.get(agent_id, f"Agent {agent_id}")
            agent_parts.append(f"{name} (`{agent_id}`)")
        lines.append(f"**Agents**: {', '.join(agent_parts)}")

    if fm.get("result"):
        outcome = fm["result"]
        label   = aliases.get(outcome, outcome)
        lines.append(f"**Outcome**: `{outcome}` ({label})" if label != outcome
                     else f"**Outcome**: `{outcome}`")

    if fm.get("evaluation_point"):
        lines.append(f"**Evaluation point**: `{fm['evaluation_point']}`")

    return "  \n".join(lines) if lines else "*No overview available.*"


def _merge_aliases(*models: ModelBlock) -> Dict[str, str]:
    """Merge aliases from multiple models, last-write-wins per key."""
    merged: Dict[str, str] = {}
    for m in models:
        merged.update(m.aliases)
    return merged


def _plenary_alias_table(models: List[ModelBlock]) -> str:
    if not models:
        return "*No models in scope.*"
    aliases = _merge_aliases(*models)
    if not aliases:
        return "*No aliases defined.*"
    rows = ["| Short | Meaning |", "|-------|---------|"]
    for k in sorted(aliases.keys(), key=lambda x: (x.isdigit(), x)):
        rows.append(f"| `{k}` | {aliases[k]} |")
    return "\n".join(rows)


# ------------------------------------------------------------------
# Dispatcher
# ------------------------------------------------------------------

def expand(
    text: str,
    doc: ALOnDocument,
    block_idx: int,
    analysis: Optional[Dict] = None,
) -> str:
    """Replace all {{shortcode ...}} in *text* with rendered markdown."""

    def _replace(m: re.Match) -> str:
        name = m.group(1)
        args = _parse_args(m.group(2))

        scope = args.get("scope", "nearest")
        model_title = args.get("model")

        # Resolve the target model(s)
        if model_title:
            target_model = doc.model_by_title(model_title)
            scope_models = [target_model] if target_model else []
        elif scope == "section":
            scope_models = doc.models_in_section(block_idx)
            target_model = doc.nearest_model(block_idx)
        elif scope == "doc":
            scope_models = doc.models()
            target_model = doc.nearest_model(block_idx)
        else:  # nearest
            target_model = doc.nearest_model(block_idx)
            scope_models = [target_model] if target_model else []

        if name == "alias_table":
            if scope in ("section", "doc") and not model_title:
                return _plenary_alias_table(scope_models)
            if target_model:
                return _alias_table(target_model)
            # No nearest model — fall back to whole-document aliases
            # (reads context blocks directly, so works even before any model)
            aliases = doc.all_aliases()
            if not aliases:
                return "*No aliases defined.*"
            rows = ["| Short | Meaning |", "|-------|---------|"]
            for k in sorted(aliases.keys(), key=lambda x: (x.isdigit(), x)):
                rows.append(f"| `{k}` | {aliases[k]} |")
            return "\n".join(rows)

        if name == "action_table":
            return _action_table(target_model) if target_model else "*No model found.*"

        if name == "opposing_table":
            return _opposing_table(target_model) if target_model else "*No model found.*"

        if name == "model_overview":
            return _model_overview(target_model) if target_model else "*No model found.*"

        if name == "results":
            return _results_render(target_model, args, analysis)

        if name == "page_break":
            return '<div style="page-break-after: always; break-after: page;"></div>'

        if name == "titleof":
            ref = args.get("ref", "")
            if ref:
                found = doc.model_by_ref(ref)
                if found is None:
                    # Fall back to title lookup
                    found = doc.model_by_title(ref)
                if found:
                    return found.title
                return f"*[unknown model ref: {ref}]*"
            return m.group(0)

        return m.group(0)  # unknown shortcode — leave as-is

    return _SHORTCODE_RE.sub(_replace, text)


def _results_render(
    model: Optional[ModelBlock],
    args: Dict[str, str],
    analysis: Optional[Dict],
) -> str:
    if model is None:
        return "*No model found for results.*"

    title = model.title or "unnamed"

    if analysis is None or title not in analysis or analysis[title] is None:
        eval_pt = args.get("eval", "")
        target  = args.get("target", "")
        spec    = ""
        if eval_pt:
            spec += f" eval=`{eval_pt}`"
        if target:
            spec += f" target=`{target}`"
        return (f"*[Results for **{title}**{spec} — "
                f"run with `--run-analysis` to populate]*")

    alo_model, satisfied_ids, eval_points = analysis[title]
    from ._runner import format_results
    return format_results(
        alo_model,
        satisfied_ids,
        eval_points,
        eval_filter=args.get("eval") or None,
        target_filter=args.get("target") or None,
    )
