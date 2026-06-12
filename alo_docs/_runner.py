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

def _run_layered(model, ness_empty_sufficient: bool = True) -> Tuple[object, Set[str], list]:
    """Run analysis on a ALOModel. Returns (model, satisfied_ids, eval_points)."""
    from alo_translator.serializers.datalog_index import DatalogIndexSerializer
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
        serializer = DatalogIndexSerializer(
            model, evaluation_history=ehist, evaluation_moment=emom,
            ness_empty_sufficient=ness_empty_sufficient,
        )
        results = serializer.evaluate()
        all_satisfied.update(qid for qid, r in results.items() if r.get("result"))
    model.queries = all_queries
    return model, all_satisfied, eval_points


def _run_flat(model, partial_spec: dict,
              ness_empty_sufficient: Optional[bool] = None) -> Tuple[object, Set[str], list]:
    """Run analysis on a TD=1 ALOModel. Returns (model, satisfied_ids, eval_points).

    ness_empty_sufficient overrides the front-matter value when provided explicitly.
    """
    from alo_translator.serializers.datalog_index import DatalogIndexSerializer
    from streamlit_app.utils import setup_queries
    from alo_translator.query_generation import _sanitize_id as _qsanitize

    yaml_evals = partial_spec.get("res_analyse", [])
    if yaml_evals:
        raw_eval_points = []
        for item in yaml_evals:
            if len(item) >= 2:
                ep, tgt = str(item[0]), str(item[1])
                em = ep.split("/")[0] if "/" in ep else "m"
                eh = ep.split("/")[1] if "/" in ep else ep
                raw_eval_points.append((em, eh, tgt))
    else:
        result_prop = partial_spec.get("result", "q")
        eval_point  = partial_spec.get("evaluation_point", "m/h1")
        eval_mom    = eval_point.split("/")[0] if "/" in eval_point else eval_point
        eval_hist   = eval_point.split("/")[1] if "/" in eval_point else "h1"
        raw_eval_points = [(eval_mom, eval_hist, result_prop)]

    if ness_empty_sufficient is None:
        ness_empty_sufficient = partial_spec.get("ness_empty_sufficient", True)

    all_satisfied: Set[str] = set()
    all_queries = []
    for em, eh, tgt in raw_eval_points:
        model.queries = []
        model = setup_queries(model, tgt, eh)
        # Scope query IDs with history to prevent collision across eval points
        eh_tag = _qsanitize(eh)
        for q in model.queries:
            if q.query_id:
                q.query_id = f"{q.query_id}_{eh_tag}"
        all_queries.extend(model.queries)
        serializer = DatalogIndexSerializer(model, evaluation_history=eh,
                                            ness_empty_sufficient=ness_empty_sufficient)
        results = serializer.evaluate()
        all_satisfied.update(qid for qid, r in results.items() if r.get("result"))

    model.queries = all_queries
    return model, all_satisfied, raw_eval_points


def _run_evaluate(model, partial_spec: dict,
                  ness_empty_sufficient: Optional[bool] = None) -> Tuple[object, Set[str], list]:
    """Run direct formula evaluation for the `evaluate` key.

    Each [index, formula] pair is evaluated as-is at the given index —
    no responsibility query generation, no X-wrapping.
    Returns (model, satisfied_ids, eval_points) where eval_points are (em, eh, formula).
    """
    from alo_translator.serializers.datalog_index import DatalogIndexSerializer
    from alo_translator.model.core import Query
    from alo_translator.parsers.builder import parse_queries, expand_queries
    from alo_translator.query_generation import _sanitize_id as _qsanitize

    yaml_evals = partial_spec.get("evaluate", [])
    if not yaml_evals:
        return model, set(), []

    if ness_empty_sufficient is None:
        ness_empty_sufficient = partial_spec.get("ness_empty_sufficient", True)

    raw_eval_points = []
    for item in yaml_evals:
        if len(item) >= 2:
            ep, formula = str(item[0]), str(item[1])
            eh = ep.split("/")[-1] if "/" in ep else ep
            raw_eval_points.append((ep, eh, formula))

    all_satisfied: Set[str] = set()
    all_queries = []
    for ep, eh, formula in raw_eval_points:
        qid = _qsanitize(f"eval_{formula}_{eh}")
        q = Query(formula_string=formula, query_id=qid)
        model.queries = [q]
        model = parse_queries(model)
        model = expand_queries(model)
        all_queries.append(model.queries[0])
        serializer = DatalogIndexSerializer(model, evaluation_history=eh,
                                            ness_empty_sufficient=ness_empty_sufficient)
        results = serializer.evaluate()
        all_satisfied.update(qid for qid, r in results.items() if r.get("result"))

    model.queries = all_queries
    return model, all_satisfied, raw_eval_points


def format_evaluate_results(model, satisfied_ids: Set[str], eval_points: list) -> str:
    """Format direct `evaluate` results as a simple markdown table."""
    from alo_translator.query_generation import _sanitize_id

    if not eval_points:
        return ""

    lines = ["| Index | Formula | Holds |", "|-------|---------|-------|"]
    for ep, eh, formula in eval_points:
        qid = _sanitize_id(f"eval_{formula}_{eh}")
        holds = "✓" if qid in satisfied_ids else "✗"
        lines.append(f"| `{ep}` | `{formula}` | {holds} |")
    return "\n".join(lines)


def run_doc_analysis(doc: ALOnDocument) -> Dict[str, Optional[Dict[bool, Tuple]]]:
    """Analyse every ModelBlock in *doc*.

    Returns a dict keyed by model title (falling back to index).
    Each value is a dict keyed by the ness_empty_sufficient bool:
        { title: { True: (alo_model, satisfied_ids, eval_pts),
                   False: (alo_model, satisfied_ids, eval_pts) } }

    Both semantics are always computed so that {{results ness_empty_sufficient="false"}}
    can be used in shortcodes without needing a duplicate model block.
    """
    import os, sys
    # dbt_parser uses a relative path for the grammar; run from repo root
    repo_root = os.path.dirname(os.path.dirname(__file__))
    old_cwd = os.getcwd()
    os.chdir(repo_root)

    try:
        from alo_translator.parsers.dbt_parser import parse_dbt_diagram
        from alo_translator.model.core import ALOModel
    finally:
        os.chdir(old_cwd)

    # Keyed by id(block) so duplicate titles don't collide.
    results: Dict[int, Optional[Dict]] = {}
    os.chdir(repo_root)
    try:
        for idx, block in enumerate(doc.models()):
            key = id(block)
            try:
                text = _block_to_mermaid_text(block)
                model_results: Dict = {}
                for ness_val in (True, False):
                    # Re-parse for each variant: _run_* mutates the model
                    parsed = parse_dbt_diagram(text)
                    if isinstance(parsed, ALOModel):
                        m, satisfied, eval_pts = _run_layered(
                            parsed, ness_empty_sufficient=ness_val)
                    else:
                        m, partial_spec = parsed
                        m, satisfied, eval_pts = _run_flat(
                            m, partial_spec, ness_empty_sufficient=ness_val)
                    model_results[ness_val] = (m, satisfied, eval_pts)

                # Direct evaluate (ness-independent)
                parsed = parse_dbt_diagram(text)
                if not isinstance(parsed, ALOModel):
                    m_ev, partial_spec_ev = parsed
                    if partial_spec_ev.get("evaluate"):
                        m_ev, sat_ev, pts_ev = _run_evaluate(m_ev, partial_spec_ev)
                        model_results["evaluate"] = (m_ev, sat_ev, pts_ev)

                results[key] = model_results
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

    from alo_translator.model.core import ALOModel
    is_layered = isinstance(model, ALOModel)

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
            prop_id = _sanitize_id(f"{emom}_{ehist}_{outcome}")
        else:
            prop_id = _sanitize_id(f"{etgt}_{ehist}")
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
