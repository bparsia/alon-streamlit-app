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

    # Agents -- derived from the parsed diagram (succ edges), not frontmatter.
    try:
        from alo_translator.parsers.dbt_parser import parse_dbt_diagram
        from ._runner import _block_to_mermaid_text
        parsed = parse_dbt_diagram(_block_to_mermaid_text(model))
        agent_ids = parsed.get_all_agents()
    except Exception:
        agent_ids = set()
    if agent_ids:
        agent_parts = []
        for agent_id in sorted(agent_ids, key=lambda x: (not x.isdigit(), x)):
            name = aliases.get(agent_id, f"Agent {agent_id}")
            agent_parts.append(f"{name} (`{agent_id}`)")
        lines.append(f"**Agents**: {', '.join(agent_parts)}")

    res_analyse = fm.get("res_analyse") or []
    if res_analyse:
        points = []
        for item in res_analyse:
            if len(item) >= 2:
                ep, tgt = str(item[0]), str(item[1])
                label = aliases.get(tgt, tgt)
                tgt_str = f"`{tgt}` ({label})" if label != tgt else f"`{tgt}`"
                points.append(f"`{ep}` → {tgt_str}")
        if points:
            lines.append(f"**Evaluation points**: {', '.join(points)}")

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

    # Resolve ness_empty_sufficient: shortcode arg > model front matter > True
    ness_arg = args.get("ness_empty_sufficient", "").strip().lower()
    if ness_arg in ("false", "no", "0"):
        ness_val = False
    elif ness_arg in ("true", "yes", "1"):
        ness_val = True
    else:
        fm_val = model.resolved_fm.get("ness_empty_sufficient", True)
        ness_val = bool(fm_val) if not isinstance(fm_val, bool) else fm_val

    # Analysis is keyed by id(block) to handle duplicate titles correctly.
    model_key = id(model)
    if analysis is None or model_key not in analysis or analysis[model_key] is None:
        eval_pt = args.get("eval", "")
        target  = args.get("target", "")
        spec    = ""
        if eval_pt:
            spec += f" eval=`{eval_pt}`"
        if target:
            spec += f" target=`{target}`"
        if ness_arg:
            spec += f" ness_empty_sufficient=`{ness_arg}`"
        return (f"*[Results for **{title}**{spec} — "
                f"run with `--run-analysis` to populate]*")

    # analysis[model_key] is {True: (model, sat, pts), False: (model, sat, pts)}
    variant = analysis[model_key].get(ness_val)
    if variant is None:
        return f"*[No analysis variant for ness_empty_sufficient={ness_val}]*"

    alo_model, satisfied_ids, eval_points = variant
    from ._runner import format_results
    return format_results(
        alo_model,
        satisfied_ids,
        eval_points,
        eval_filter=args.get("eval") or None,
        target_filter=args.get("target") or None,
    )
