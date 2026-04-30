"""Analysis runner — parse models in a document and run responsibility analysis."""

from __future__ import annotations
import re
import sys
from collections import defaultdict
from typing import Dict, Optional, Set, Tuple

import yaml

from .document import ALOnDocument, ModelBlock


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _block_to_mermaid_text(block: ModelBlock) -> str:
    """Produce front-matter + diagram text (no fence lines) for the parser."""
    fm = block.resolved_fm if block.resolved_fm else block.front_matter
    fm_yaml = yaml.dump(fm, default_flow_style=False, allow_unicode=True).rstrip()
    return f"---\n{fm_yaml}\n---\n{block.diagram}"


# ──────────────────────────────────────────────────────────────────────────────
# Analysis
# ──────────────────────────────────────────────────────────────────────────────

def _run_layered(model) -> Tuple[object, Set[str], list]:
    """Run analysis on a LayeredALOModel. Returns (model, satisfied_ids, eval_points)."""
    from alo_translator.serializers.layered_datalog_index import LayeredDatalogIndexSerializer
    from streamlit_app.utils import setup_layered_queries

    eval_points = model.evaluations or [
        (model.evaluation_moment, model.evaluation_history, model.target_proposition)
    ]
    all_satisfied: Set[str] = set()
    all_queries = []
    for emom, ehist, etgt in eval_points:
        model.evaluation_moment = emom
        model.evaluation_history = ehist
        model.target_proposition = etgt
        model.queries = []
        model = setup_layered_queries(model)
        all_queries.extend(model.queries)
        serializer = LayeredDatalogIndexSerializer(
            model, evaluation_history=ehist, evaluation_moment=emom
        )
        results = serializer.evaluate()
        all_satisfied.update(qid for qid, r in results.items() if r.get("result"))
    model.queries = all_queries
    return model, all_satisfied, eval_points


def _run_flat(model, partial_spec: dict) -> Tuple[object, Set[str], list]:
    """Run analysis on a TD=1 ALOModel. Returns (model, satisfied_ids, eval_points)."""
    from alo_translator.serializers.datalog_index import DatalogIndexSerializer
    from streamlit_app.utils import setup_queries

    result_prop = partial_spec.get("result", "q")
    eval_point  = partial_spec.get("evaluation_point", "m/h1")
    eval_mom    = eval_point.split("/")[0] if "/" in eval_point else eval_point
    eval_hist   = eval_point.split("/")[1] if "/" in eval_point else "h1"

    model = setup_queries(model, result_prop, eval_hist)
    serializer = DatalogIndexSerializer(model, evaluation_history=eval_hist)
    results = serializer.evaluate()
    satisfied = {qid for qid, r in results.items() if r.get("result")}
    return model, satisfied, [(eval_mom, eval_hist, result_prop)]


def run_doc_analysis(doc: ALOnDocument) -> Dict[str, Tuple]:
    """Analyse every ModelBlock in *doc*.

    Returns a dict keyed by model title (falling back to index):
        { title: (alo_model, satisfied_ids) }
    """
    import os, sys
    # dbt_parser uses a relative path for the grammar; run from repo root
    repo_root = os.path.dirname(os.path.dirname(__file__))
    old_cwd = os.getcwd()
    os.chdir(repo_root)

    try:
        from alo_translator.parsers.dbt_parser import parse_dbt_diagram
        from alo_translator.model.core import LayeredALOModel
    finally:
        os.chdir(old_cwd)

    results: Dict[str, Tuple] = {}
    os.chdir(repo_root)
    try:
        for idx, block in enumerate(doc.models()):
            key = block.title or f"model_{idx}"
            try:
                text = _block_to_mermaid_text(block)
                parsed = parse_dbt_diagram(text)
                if isinstance(parsed, LayeredALOModel):
                    model, satisfied, eval_pts = _run_layered(parsed)
                else:
                    model, partial_spec = parsed
                    model, satisfied, eval_pts = _run_flat(model, partial_spec)
                results[key] = (model, satisfied, eval_pts)
            except Exception as e:
                print(f"[alo_docs] analysis failed for '{key}': {e}", file=sys.stderr)
                results[key] = None
    finally:
        os.chdir(old_cwd)

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Formatting
# ──────────────────────────────────────────────────────────────────────────────

def format_results(
    model,
    satisfied_ids: Set[str],
    eval_points: list,
    eval_filter: Optional[str] = None,
    target_filter: Optional[str] = None,
) -> str:
    """Format responsibility results as markdown.

    If *eval_filter* or *target_filter* are given, only the matching evaluation
    points are rendered.
    """
    from alo_translator.query_generation import _sanitize_id

    aliases = model.aliases if hasattr(model, "aliases") else {}

    # Apply filters
    if eval_filter or target_filter:
        eval_points = [
            (em, eh, et) for em, eh, et in eval_points
            if (eval_filter is None or f"{em}/{eh}" == eval_filter)
            and (target_filter is None or et == target_filter)
        ]

    if not eval_points:
        return f"*No matching evaluation point for eval={eval_filter!r} target={target_filter!r}.*"

    from alo_translator.model.core import LayeredALOModel
    is_layered = isinstance(model, LayeredALOModel)

    sections = []
    for emom, ehist, etgt in eval_points:
        if etgt.startswith("do("):
            x_count = 1
        elif re.match(r"^X+do\(", etgt):
            x_count = len(re.match(r"^(X+)", etgt).group(1))
        else:
            x_count = 1
        outcome = "X" * x_count + etgt
        if is_layered:
            prop_id = _sanitize_id(f"{emom}_{outcome}")
        else:
            prop_id = _sanitize_id(etgt)
        suffix = f"_{prop_id}"

        agent_results = defaultdict(lambda: {
            "pres": False, "sres": False, "res": False,
            "but": False, "ness": False,
        })
        for query in model.queries:
            qid = query.query_id
            if not qid or not qid.endswith(suffix):
                continue
            middle = qid[len("q_"):-len(suffix)]
            parts = middle.split("_", 1)
            if len(parts) < 2:
                continue
            resp_type, agent_str = parts[0], parts[1]
            if resp_type in ("but", "ness"):
                m = re.match(r"^([a-zA-Z]+)(\d+)$", agent_str)
                if m:
                    agent_str = m.group(2)
            if resp_type in agent_results[agent_str]:
                agent_results[agent_str][resp_type] = qid in satisfied_ids

        tgt_desc = aliases.get(etgt, etgt)
        lines = [
            f"**`{emom}/{ehist}`** → `{etgt}` ({tgt_desc})",
            "",
            "| Agent | pres | sres | res | but | ness |",
            "|-------|------|------|-----|-----|------|",
        ]
        for agent in sorted(agent_results.keys(), key=lambda x: (len(x.split("_")), x)):
            r = agent_results[agent]
            if "_" in agent:
                names = [aliases.get(aid, aid) for aid in agent.split("_")]
                display = "{" + ", ".join(names) + "}"
            else:
                display = aliases.get(agent, agent)
            row = [display] + ["✓" if r[k] else " "
                                for k in ("pres", "sres", "res", "but", "ness")]
            lines.append("| " + " | ".join(row) + " |")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)
