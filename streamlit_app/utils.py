"""
Shared utilities for the ALOn Streamlit app.

Provides model formatting, analysis backends, and UI helpers
that are reusable across pages.
"""

import json
import tempfile
from pathlib import Path
from typing import Dict, Optional, Set
import re
from collections import defaultdict

import streamlit as st
import streamlit.components.v1 as components

from alo_translator.parsers.dbt_parser import parse_dbt_diagram
from alo_translator.parsers.builder import parse_queries
from alo_translator.query_generation import ResponsibilityConfig, generate_queries
from alo_translator.serializers.datalog_index import DatalogIndexSerializer

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
    """Return Konclude binary path if configured via Streamlit secret, else None.

    Set KONCLUDE_PATH in .streamlit/secrets.toml when running locally.
    Leave unset on Streamlit Cloud to disable the Konclude option.
    """
    if not _KONCLUDE_IMPORTS_OK:
        return None
    try:
        p = Path(st.secrets["KONCLUDE_PATH"])
        if p.exists():
            return p
    except (KeyError, Exception):
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


def format_results_table(model, satisfied_query_ids: Set[str], result_prop: str) -> str:
    """Format responsibility results as a markdown table."""
    agent_results = defaultdict(lambda: {
        "pres": False, "sres": False, "res": False,
        "dxstit": False, "but": False, "ness": False,
    })
    action_legend = {}

    for query in model.queries:
        qid = query.query_id
        parts = qid.split("_")
        if len(parts) < 3:
            continue
        resp_type = parts[1]
        agent_str = "_".join(parts[2:-1])

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

    if action_legend:
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
