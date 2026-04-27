"""
Shared utilities for the ALOn Streamlit app.

Provides model formatting, analysis backends, and UI helpers
that are reusable across pages.
"""

import json
import tempfile
from pathlib import Path
from typing import Dict, Optional, Set, Tuple, Any
import re
from collections import defaultdict

import streamlit as st
import streamlit.components.v1 as components

from alo_translator.parsers.dbt_parser import parse_dbt_diagram
from alo_translator.parsers.builder import parse_queries
from alo_translator.query_generation import ResponsibilityConfig, generate_queries
from alo_translator.serializers.datalog_index import DatalogIndexSerializer
from alo_translator.model.core import LayeredALOModel, Query
from alo_translator.serializers.layered_datalog_index import LayeredDatalogIndexSerializer
from alo_translator.serializers.layered_owl_index import LayeredOWLIndexSerializer

def _sanitize_id(s: str) -> str:
    """Convert a formula string to a safe query-ID suffix (mirrors query_generation._sanitize_id)."""
    result = re.sub(r'[(){}\[\],: ]', '_', s)
    result = re.sub(r'_+', '_', result)
    return result.strip('_')


# Konclude imports — only available when running locally with the binary present
try:
    from alo_translator.serializers.owl_index_new_expander import OWLIndexNewExpanderSerializer
    from alo_translator.serializers.index_strategies import EquivFullCardinalityStrategy
    from alo_translator.reasoners.konclude import KoncludeAdapter
    from alo_translator.reasoners.base import ReasoningMode
    _KONCLUDE_IMPORTS_OK = True
except ImportError:
    _KONCLUDE_IMPORTS_OK = False


# ---------------------------------------------------------------------------
# Backend helpers
# ---------------------------------------------------------------------------

def konclude_path() -> Optional[Path]:
    """Return Konclude binary path, or None if not available.

    Discovery order:
    1. KONCLUDE_PATH in .streamlit/secrets.toml (Streamlit Cloud / local override)
    2. reasoner_config.toml in project root or next to this file (local dev)
    """
    if not _KONCLUDE_IMPORTS_OK:
        return None

    # 1. Streamlit secrets
    try:
        p = Path(st.secrets["KONCLUDE_PATH"])
        if p.exists():
            return p
    except (KeyError, Exception):
        pass

    # 2. reasoner_config.toml
    try:
        from alo_translator.reasoners.config import load_config
        for config_path in [
            Path("reasoner_config.toml"),
            Path(__file__).parent / "reasoner_config.toml",
            Path(__file__).parent.parent / "reasoner_config.toml",
        ]:
            try:
                config = load_config(config_path)
                raw = config.reasoners["konclude"].path
                if not raw:
                    continue
                p = Path(raw)
                if not p.is_absolute():
                    p = config_path.parent / p
                if p.is_file():
                    return p
            except Exception:
                continue
    except ImportError:
        pass

    return None


def setup_queries(model, result_prop: str, eval_history: str):
    """Attach responsibility config, generate and parse queries. Mutates model."""
    model.responsibility_config = ResponsibilityConfig(
        target_proposition=result_prop,
        agents="all",
        groups="all",
        responsibility_types=["pres", "sres", "res", "dxstit", "but", "ness"],
        history=eval_history,
    )
    queries = generate_queries(model)
    model.queries.extend(queries)
    return parse_queries(model)


def analysis_button(key: str, model, partial_spec: dict, label: str = "▶️ Run Analysis",
                    show_legend: bool = True) -> None:
    """
    Render a self-contained analysis button that persists results across reruns.

    Args:
        key: Unique session_state key for this analysis (e.g. "tut_analysis_1").
        model: Parsed ALOn model.
        partial_spec: Spec dict from parse_dbt_diagram (provides result/eval_point).
        label: Button label text.
    """
    if st.button(label, key=f"btn_{key}"):
        with st.spinner("Running…"):
            result_prop  = partial_spec.get("result", "q")
            eval_point   = partial_spec.get("evaluation_point", "m/h1")
            eval_history = eval_point.split("/")[1] if "/" in eval_point else "h1"
            satisfied    = run_analysis_datalog(model, result_prop, eval_history)
            if satisfied is not None:
                # Store the rendered markdown — model.queries won't survive the rerun
                st.session_state[key] = format_results_table(model, satisfied, result_prop,
                                                              show_legend=show_legend)

    if key in st.session_state:
        results_md = st.session_state[key]
        col_r, col_rb = st.columns([8, 1])
        with col_r:
            st.markdown(results_md)
        with col_rb:
            copy_button(results_md, "📋 Copy")


def run_analysis_datalog(model, result_prop: str, eval_history: str) -> Optional[Set[str]]:
    """Run responsibility analysis using pyDatalog. Returns satisfied query IDs."""
    try:
        model = setup_queries(model, result_prop, eval_history)
        serializer = DatalogIndexSerializer(model, evaluation_history=eval_history)
        results = serializer.evaluate()
        return {qid for qid, r in results.items() if r.get("result")}
    except Exception as e:
        st.error(f"Analysis error: {e}")
        return None


def parse_model(mermaid_text: str) -> Tuple[Any, Dict]:
    """
    Parse a Mermaid diagram and return (model, partial_spec).

    For TD=1 diagrams parse_dbt_diagram returns (ALOModel, dict).
    For TD>1 diagrams it returns LayeredALOModel directly.
    This normalizes both cases.
    """
    result = parse_dbt_diagram(mermaid_text)
    if isinstance(result, LayeredALOModel):
        return result, {}
    return result  # (ALOModel, partial_spec) tuple


def _target_x_count(model: LayeredALOModel) -> int:
    """Number of X steps from the evaluation moment to when the target is true.

    For do(α) targets the action is performed one step ahead of the eval moment.
    For propositional atoms the target lives at the leaves.
    """
    tgt = model.target_proposition
    if tgt.startswith('do('):
        return 1
    m = re.match(r'^(X+)do\(', tgt)
    if m:
        return len(m.group(1))
    eval_depth = model.moments[model.evaluation_moment].depth
    return model.depth() - eval_depth


def _outcome_formula(model: LayeredALOModel) -> str:
    """Return the outcome formula for display (e.g. 'Xdo(sd1)' or 'Xq')."""
    x_count = _target_x_count(model)
    return 'X' * x_count + model.target_proposition


def _operator_formula(model: LayeredALOModel) -> str:
    """Return the formula to pass to responsibility operators.

    All operators (pres/sres/res/but/ness) internally add one X step,
    so the formula should have one fewer X than the raw target depth.
    """
    x_count = _target_x_count(model)
    inner_x = max(0, x_count - 1)
    return 'X' * inner_x + model.target_proposition


def setup_layered_queries(model: LayeredALOModel) -> LayeredALOModel:
    """Attach responsibility queries to a LayeredALOModel for analysis."""
    from alo_translator.query_generation import _sanitize_id
    outcome = _outcome_formula(model)
    op_formula = _operator_formula(model)
    prop_id = _sanitize_id(outcome)

    agents_at_eval = sorted(model.available_actions_at(model.evaluation_moment).keys())
    resp_types = ["pres", "sres", "res"]

    queries = []
    for agent in agents_at_eval:
        for rt in resp_types:
            qid = f"q_{rt}_{agent}_{prop_id}"
            queries.append(Query(f"[{agent} {rt}]{op_formula}", query_id=qid))
        # but/ness for individual agents
        hp = model.histories.get(model.evaluation_history)
        if hp:
            acts_at_eval = hp.actions_at.get(model.evaluation_moment, {})
            if agent in acts_at_eval:
                action_str = f"{acts_at_eval[agent]}{agent}"
                queries.append(Query(f"but({action_str}, {op_formula})",
                                     query_id=f"q_but_{action_str}_{prop_id}"))
                queries.append(Query(f"ness({action_str}, {op_formula})",
                                     query_id=f"q_ness_{action_str}_{prop_id}"))

    model.queries = queries
    return model


def run_analysis_datalog_layered(model: LayeredALOModel) -> Optional[Set[str]]:
    """Run responsibility analysis on a LayeredALOModel using pyDatalog.

    If model.evaluations is set, runs each (moment, history, target) separately
    and unions the satisfied query IDs. Accumulates all queries on model.queries
    so format_layered_results_table can display each section correctly.
    """
    try:
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
            serializer = LayeredDatalogIndexSerializer(model,
                                                       evaluation_history=ehist,
                                                       evaluation_moment=emom)
            results = serializer.evaluate()
            all_satisfied.update(qid for qid, r in results.items() if r.get("result"))
        model.queries = all_queries
        return all_satisfied
    except Exception as e:
        st.error(f"Analysis error: {e}")
        return None


def run_analysis_konclude_layered(model: LayeredALOModel) -> Optional[Set[str]]:
    """Run responsibility analysis on a LayeredALOModel using Konclude (OWL).

    Mirrors run_analysis_datalog_layered but uses LayeredOWLIndexSerializer
    and the Konclude reasoner.  Iterates over model.evaluations like the
    pyDatalog path so results are merged across all evaluation points.
    """
    try:
        from alo_translator.serializers.index_strategies import EquivFullCardinalityStrategy
        from alo_translator.reasoners.konclude import KoncludeAdapter
        from alo_translator.reasoners.base import ReasoningMode

        bin_path = konclude_path()
        if bin_path is None:
            st.error("Konclude binary not found.")
            return None

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

            strategy = EquivFullCardinalityStrategy()
            serializer = LayeredOWLIndexSerializer(
                model,
                evaluation_moment=emom,
                evaluation_history=ehist,
                strategy=strategy,
            )
            owl_output = serializer.serialize()

            with tempfile.NamedTemporaryFile(mode="w", suffix=".owl", delete=False) as f:
                f.write(owl_output)
                temp_path = Path(f.name)

            try:
                adapter = KoncludeAdapter(bin_path)
                result = adapter.run(temp_path, ReasoningMode.REALISATION,
                                     timeout=300, verbose=False)
                if not result.success:
                    st.error(f"Reasoner failed: {result.error_message}")
                    return None
                eval_idx = f"{emom}_{ehist}"
                m_types = result.individual_types.get(eval_idx, set())
                all_satisfied.update(
                    q.query_id for q in model.queries
                    if q.query_id and q.query_id in m_types
                )
            finally:
                temp_path.unlink()

        model.queries = all_queries
        return all_satisfied
    except Exception as e:
        st.error(f"Konclude analysis error: {e}")
        return None


def format_layered_model_overview(model: LayeredALOModel) -> str:
    """Format a LayeredALOModel overview as markdown."""
    lines = []
    aliases = model.aliases

    lines.append("### Agents & Actions per Moment")
    for moment_name, node in sorted(model.moments.items(), key=lambda kv: kv[1].depth):
        if not node.available_actions:
            continue
        parts = []
        for agent, acts in sorted(node.available_actions.items()):
            name = aliases.get(agent, f"Agent {agent}")
            act_strs = [f"`{a}{agent}`" for a in acts]
            parts.append(f"**{name}**: {', '.join(act_strs)}")
        lines.append(f"- `{moment_name}` (depth {node.depth}): {'; '.join(parts)}")

    if model.opposings:
        lines.append("\n### Opposing Relations")
        for opp in model.opposings:
            opposed = str(opp.opposed_action)
            opposing = str(opp.opposing_action)
            lines.append(f"- `{opposed}` opposed by `{opposing}`")

    lines.append(f"\n### Histories ({len(model.histories)} total)\n")
    lines.append("| History | Path | Actions |")
    lines.append("|---------|------|---------|")
    for hname, hp in sorted(model.histories.items()):
        path_str = " → ".join(hp.path)
        acts_parts = []
        for mom, acts in sorted(hp.actions_at.items()):
            act_strs = [f"{at}{ag}" for ag, at in sorted(acts.items())]
            acts_parts.append(f"{mom}: {','.join(act_strs)}")
        lines.append(f"| {hname} | {path_str} | {'; '.join(acts_parts)} |")

    # Outcome propositions
    leaf_props = [(name, node.propositions)
                  for name, node in model.moments.items()
                  if node.is_leaf and node.propositions]
    if leaf_props:
        lines.append("\n### Leaf Propositions")
        for mom, props in sorted(leaf_props):
            lines.append(f"- `{mom}`: {', '.join(sorted(props))}")

    return "\n".join(lines)


def format_layered_results_table(model: LayeredALOModel, satisfied_ids: Set[str]) -> str:
    """Format LayeredALOModel responsibility results as markdown.

    Groups results by evaluation point when multiple evaluations are present.
    """
    from alo_translator.query_generation import _sanitize_id
    aliases = model.aliases

    eval_points = model.evaluations or [
        (model.evaluation_moment, model.evaluation_history, model.target_proposition)
    ]

    sections = []
    for emom, ehist, etgt in eval_points:
        if etgt.startswith('do('):
            x_count = 1
        elif re.match(r'^X+do\(', etgt):
            x_count = len(re.match(r'^(X+)', etgt).group(1))
        else:
            x_count = model.depth() - model.moments[emom].depth
        outcome = 'X' * x_count + etgt
        prop_id = _sanitize_id(outcome)
        suffix = f"_{prop_id}"

        agent_results = defaultdict(lambda: {
            "pres": False, "sres": False, "res": False, "but": False, "ness": False,
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
        for agent in sorted(agent_results.keys()):
            r = agent_results[agent]
            display = aliases.get(agent, f"Agent {agent}")
            row = [display] + ["✓" if r[k] else " " for k in ("pres", "sres", "res", "but", "ness")]
            lines.append("| " + " | ".join(row) + " |")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def run_analysis_konclude(model, result_prop: str, eval_history: str) -> Optional[Set[str]]:
    """Run responsibility analysis using Konclude OWL reasoner. Returns satisfied query IDs."""
    try:
        model = setup_queries(model, result_prop, eval_history)

        strategy = EquivFullCardinalityStrategy()
        serializer = OWLIndexNewExpanderSerializer(model, strategy=strategy)
        owl_output = serializer.serialize()

        bin_path = konclude_path()
        if bin_path is None:
            st.error("Konclude binary not found.")
            return None

        with tempfile.NamedTemporaryFile(mode="w", suffix=".owl", delete=False) as f:
            f.write(owl_output)
            temp_path = Path(f.name)

        try:
            adapter = KoncludeAdapter(bin_path)
            result = adapter.run(temp_path, ReasoningMode.REALISATION, timeout=300, verbose=False)
            if not result.success:
                st.error(f"Reasoner failed: {result.error_message}")
                return None
            eval_individual = f"m_{eval_history}"
            m_types = result.individual_types.get(eval_individual, set())
            return {q.query_id for q in model.queries if q.query_id in m_types}
        finally:
            temp_path.unlink()

    except Exception as e:
        st.error(f"Analysis error: {e}")
        return None


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def load_example_models() -> Dict[str, str]:
    """Load example models from the models/ directory next to this file."""
    models_dir = Path(__file__).parent / "models"
    if not models_dir.exists():
        return {}
    return {
        f.stem: f.read_text()
        for f in sorted(models_dir.glob("*.mmd"))
    }


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_model_overview(model) -> str:
    """Format model overview (agents, opposings, history table) as markdown."""
    lines = []
    aliases = model.aliases

    lines.append("### Agents")
    for agent_id in sorted(model.agents_actions.keys()):
        agent_name = aliases.get(agent_id, f"Agent {agent_id}")
        action_strs = [
            f"`{a}` ({aliases[a]})" if a in aliases else f"`{a}`"
            for a in model.agents_actions[agent_id]
        ]
        lines.append(f"- **{agent_name}** (`{agent_id}`): {', '.join(action_strs)}")

    if model.opposings:
        lines.append("\n### Opposing Relations")
        for opp in model.opposings:
            opposed  = f"{opp.opposed_action.action_type}{opp.opposed_action.agent}"
            opposing = f"{opp.opposing_action.action_type}{opp.opposing_action.agent}"
            opposed_desc  = aliases.get(opp.opposed_action.action_type,  opp.opposed_action.action_type)
            opposing_desc = aliases.get(opp.opposing_action.action_type, opp.opposing_action.action_type)
            lines.append(f"- `{opposed}` ({opposed_desc}) opposed by `{opposing}` ({opposing_desc})")

    lines.append(f"\n### Histories\n\nTotal histories: **{len(model.named_histories)}**\n")
    lines.append(format_history_table_md(model))

    return "\n".join(lines)


def format_history_table_md(model) -> str:
    """Return the history table as a markdown string."""
    lines = [
        "| History | Actions | Outcome |",
        "|---------|---------|---------|",
    ]
    for hist_name in sorted(model.named_histories.keys()):
        ga = model.named_histories[hist_name]
        result = next((r for r in model.results if r.history_name == hist_name), None)
        actions_str = ", ".join(f"{act}{ag}" for ag, act in sorted(ga.actions.items()))
        outcome_str = ", ".join(sorted(result.true_propositions)) if result else ""
        lines.append(f"| {hist_name} | {actions_str} | {outcome_str} |")
    return "\n".join(lines)


def format_results_table(model, satisfied_query_ids: Set[str], result_prop: str,
                         show_legend: bool = True) -> str:
    """Format responsibility results as a markdown table."""
    agent_results = defaultdict(lambda: {
        "pres": False, "sres": False, "res": False,
        "dxstit": False, "but": False, "ness": False,
    })
    action_legend = {}

    # Match both sanitized ("_do_sd1") and raw ("_do(sd1)") prop suffixes,
    # since old .pyc files may still generate unsanitized query IDs.
    suffix_sanitized = f"_{_sanitize_id(result_prop)}"
    suffix_raw = f"_{result_prop}"

    for query in model.queries:
        qid = query.query_id
        if qid.endswith(suffix_sanitized):
            actual_suffix = suffix_sanitized
        elif qid.endswith(suffix_raw):
            actual_suffix = suffix_raw
        else:
            continue
        # Strip "q_" prefix and "_{prop_id}" suffix to isolate resp_type + agent
        middle = qid[len("q_"):-len(actual_suffix)]
        parts = middle.split("_", 1)
        if len(parts) < 2:
            continue
        resp_type, agent_str = parts[0], parts[1]

        if resp_type in ("but", "ness"):
            m = re.match(r"^([a-zA-Z]+)(\d+)$", agent_str)
            if m:
                action_legend[m.group(2)] = agent_str
                agent_str = m.group(2)

        if resp_type in agent_results[agent_str]:
            agent_results[agent_str][resp_type] = qid in satisfied_query_ids

    aliases = model.aliases
    result_desc = aliases.get(result_prop, result_prop)

    lines = [
        f"**Outcome**: `{result_prop}` ({result_desc})",
        "",
        "| Agent/Coalition | pres | sres | res | dxstit | but | ness |",
        "|----------------|------|------|-----|--------|-----|------|",
    ]

    for agent in sorted(agent_results.keys(), key=lambda x: (len(x.split("_")), x)):
        r = agent_results[agent]
        if "_" in agent:
            names = [aliases.get(aid, aid) for aid in agent.split("_")]
            display = "{" + ", ".join(names) + "}"
        else:
            display = aliases.get(agent, agent)

        row = [display] + ["✓" if r[k] else " " for k in ("pres", "sres", "res", "dxstit", "but", "ness")]
        lines.append("| " + " | ".join(row) + " |")

    if action_legend and show_legend:
        lines.append(
            "\nNote: but/ness causation evaluated for individual or group actions done at the "
            "evaluation point. Thus, while a tick in the pres cell for 1 should be read as "
            "`[1 pres]outcome`, a tick in the but cell should be read as `but(actionDoneBy1, outcome)`."
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def copy_button(text: str, label: str = "📋 Copy") -> None:
    """Render a small copy-to-clipboard button using browser JS."""
    safe = json.dumps(text)
    components.html(f"""
        <script>
        function doCopy() {{
            var btn = document.getElementById('cpbtn');
            var text = {safe};
            if (navigator.clipboard) {{
                navigator.clipboard.writeText(text).then(function() {{
                    btn.innerText = '\u2713 Copied';
                    setTimeout(function() {{ btn.innerText = '{label}'; }}, 1800);
                }});
            }} else {{
                var el = document.createElement('textarea');
                el.value = text;
                document.body.appendChild(el);
                el.select();
                document.execCommand('copy');
                document.body.removeChild(el);
                btn.innerText = '\u2713 Copied';
                setTimeout(function() {{ btn.innerText = '{label}'; }}, 1800);
            }}
        }}
        </script>
        <button id="cpbtn" onclick="doCopy()" style="
            background:none; border:1px solid #ccc; border-radius:4px;
            padding:3px 10px; cursor:pointer; font-size:13px; color:#555;
        ">{label}</button>
    """, height=32)
