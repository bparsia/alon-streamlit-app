#!/usr/bin/env python3
"""
ALOn Model Explorer - Streamlit App

Interactive app for editing, visualizing, and reasoning over ALOn models.
"""

import streamlit as st
from streamlit_mermaid import st_mermaid
import sys
import tempfile
from pathlib import Path
from typing import Optional, Set

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from alo_translator.parsers.dbt_parser import parse_dbt_diagram
from alo_translator.parsers.builder import parse_queries, expand_queries
from alo_translator.query_generation import ResponsibilityConfig, generate_queries
from alo_translator.serializers.index_mermaid import serialize_index
from alo_translator.serializers.owl_index_new_expander import OWLIndexNewExpanderSerializer
from alo_translator.serializers.index_strategies import EquivFullCardinalityStrategy
from alo_translator.reasoners.konclude import KoncludeAdapter
from alo_translator.reasoners.base import ReasoningMode
from alo_translator.reasoners.config import load_config


# Page config
st.set_page_config(
    page_title="ALOn Model Explorer",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .stTextArea textarea {
        font-family: monospace;
        font-size: 12px;
    }
    .model-section {
        margin-top: 2rem;
    }
</style>
""", unsafe_allow_html=True)


def load_example_models():
    """Load example models from the models directory."""
    models_dir = Path(__file__).parent / "models"
    if not models_dir.exists():
        return {}

    models = {}
    for model_file in sorted(models_dir.glob("*.mmd")):
        with open(model_file, 'r') as f:
            models[model_file.stem] = f.read()
    return models


def format_model_overview(model):
    """Format model overview as markdown."""
    lines = []

    # Agents
    lines.append("### Agents")
    aliases = model.aliases
    for agent_id in sorted(model.agents_actions.keys()):
        agent_name = aliases.get(agent_id, f"Agent {agent_id}")
        actions = model.agents_actions[agent_id]
        action_strs = []
        for a in actions:
            if a in aliases:
                action_strs.append(f"`{a}` ({aliases[a]})")
            else:
                action_strs.append(f"`{a}`")
        lines.append(f"- **{agent_name}** (`{agent_id}`): {', '.join(action_strs)}")

    # Opposings
    if model.opposings:
        lines.append("\n### Opposing Relations")
        for opp in model.opposings:
            opposed = f"{opp.opposed_action.action_type}{opp.opposed_action.agent}"
            opposing = f"{opp.opposing_action.action_type}{opp.opposing_action.agent}"
            opposed_desc = aliases.get(opp.opposed_action.action_type, opp.opposed_action.action_type)
            opposing_desc = aliases.get(opp.opposing_action.action_type, opp.opposing_action.action_type)
            lines.append(f"- `{opposed}` ({opposed_desc}) opposed by `{opposing}` ({opposing_desc})")

    # Histories
    lines.append(f"\n### Histories")
    lines.append(f"\nTotal histories: **{len(model.named_histories)}**\n")
    lines.append("| History | Actions | Outcome |")
    lines.append("|---------|---------|---------|")
    for hist_name in sorted(model.named_histories.keys()):
        ga = model.named_histories[hist_name]
        result = next((r for r in model.results if r.history_name == hist_name), None)

        actions_str = ', '.join([f"{act}{ag}" for ag, act in sorted(ga.actions.items())])
        outcome_str = ', '.join(sorted(result.true_propositions)) if result else ""

        lines.append(f"| {hist_name} | {actions_str} | {outcome_str} |")

    return '\n'.join(lines)


def run_responsibility_analysis(model, result_prop: str, eval_history: str) -> Optional[Set[str]]:
    """Run responsibility analysis and return satisfied query IDs."""
    try:
        # Create responsibility config
        resp_config = ResponsibilityConfig(
            target_proposition=result_prop,
            agents="all",
            groups="all",
            responsibility_types=["pres", "sres", "res", "dxstit", "but", "ness"],
            history=eval_history
        )

        model.responsibility_config = resp_config

        # Generate and parse queries
        queries = generate_queries(model)
        model.queries.extend(queries)
        model = parse_queries(model)
        model = expand_queries(model, evaluation_history=eval_history)

        # Serialize to OWL
        strategy = EquivFullCardinalityStrategy()
        serializer = OWLIndexNewExpanderSerializer(model, strategy=strategy)
        owl_output = serializer.serialize()

        # Run Konclude
        config = load_config(Path("reasoner_config.toml"))
        konclude_path = Path(config.reasoners["konclude"].path)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.owl', delete=False) as f:
            f.write(owl_output)
            temp_owl_path = Path(f.name)

        try:
            adapter = KoncludeAdapter(konclude_path)
            result = adapter.run(temp_owl_path, ReasoningMode.REALISATION, timeout=300, verbose=False)

            if not result.success:
                st.error(f"Reasoner failed: {result.error_message}")
                return None

            # Extract satisfied queries
            eval_individual = "m_h1"
            m_types = result.individual_types.get(eval_individual, set())
            satisfied_query_ids = {q.query_id for q in model.queries if q.query_id in m_types}

            return satisfied_query_ids

        finally:
            temp_owl_path.unlink()

    except Exception as e:
        st.error(f"Analysis error: {str(e)}")
        return None


def format_results_table(model, satisfied_query_ids: Set[str], result_prop: str):
    """Format responsibility results as markdown table."""
    import re
    from collections import defaultdict

    agent_results = defaultdict(lambda: {
        'pres': False, 'sres': False, 'res': False,
        'dxstit': False, 'but': False, 'ness': False
    })

    action_legend = {}

    for query in model.queries:
        query_id = query.query_id
        satisfied = query_id in satisfied_query_ids

        parts = query_id.split('_')
        if len(parts) >= 3:
            resp_type = parts[1]
            agent_parts = parts[2:-1]
            agent_str = '_'.join(agent_parts)

            if resp_type in ('but', 'ness'):
                m = re.match(r'^([a-zA-Z]+)(\d+)$', agent_str)
                if m:
                    action_id = agent_str
                    agent_str = m.group(2)
                    action_legend[agent_str] = action_id

            if resp_type in agent_results[agent_str]:
                agent_results[agent_str][resp_type] = satisfied

    sorted_agents = sorted(agent_results.keys(), key=lambda x: (len(x.split('_')), x))

    # Get result description
    aliases = model.aliases
    result_desc = aliases.get(result_prop, result_prop)

    # Build markdown table
    lines = []
    lines.append(f"**Outcome**: `{result_prop}` ({result_desc})")
    lines.append("")
    lines.append("| Agent/Coalition | pres | sres | res | dxstit | but | ness |")
    lines.append("|----------------|------|------|-----|--------|-----|------|")

    for agent in sorted_agents:
        r = agent_results[agent]

        # Format agent name with aliases
        if '_' in agent:
            agent_ids = agent.split('_')
            agent_names = [aliases.get(aid, aid) for aid in agent_ids]
            agent_display = '{' + ', '.join(agent_names) + '}'
        else:
            agent_display = aliases.get(agent, agent)

        pres = "✓" if r['pres'] else " "
        sres = "✓" if r['sres'] else " "
        res = "✓" if r['res'] else " "
        dxstit = "✓" if r['dxstit'] else " "
        but = "✓" if r['but'] else " "
        ness = "✓" if r['ness'] else " "

        lines.append(f"| {agent_display} | {pres} | {sres} | {res} | {dxstit} | {but} | {ness} |")

    # Add legend
    if action_legend:
        lines.append("")
        legend_parts = []
        for ag, act in sorted(action_legend.items()):
            agent_name = aliases.get(ag, ag)
            action_name = aliases.get(act[:len(act)-len(ag)], act[:len(act)-len(ag)])
            legend_parts.append(f"{agent_name} → {action_name}")
        lines.append(f"Note: but/ness causation evaluated for individual or group actions done at the evaluation point. Thus, while a tick in the pres cell for 1 should be read as `[1 pres]outcome`, a tick in the but cell should be read as `but(actionDoneBy1, outcome)`.")

    return '\n'.join(lines)


def main():
    st.title("🌳 ALOn Model Explorer")
    st.markdown("Interactive tool for editing, visualizing, and reasoning over ALOn models")

    st.markdown("""You may load an enter either a Discrete Branching Time or and Index style model. The model can also be *partially* specified in the following ways:

1. One can omit some complete group actions and thus associated histories. You must always designate h1 (the history where responsibility will be evaluated) and any additional ones you wish to specify should be consecutatively numbered.
2. If some successor moment is omited, it will get the negation of the target outcome by default.
""")
    # Sidebar - Model Repository
    with st.sidebar:
        st.header("📚 Model Repository")

        # Load examples
        example_models = load_example_models()

        if example_models:
            st.subheader("Example Models")
            selected_example = st.selectbox(
                "Load example",
                [""] + list(example_models.keys()),
                format_func=lambda x: "Select an example..." if x == "" else x
            )

            if selected_example and st.button("Load"):
                st.session_state.mermaid_input = example_models[selected_example]
                # Also update the editor's state
                st.session_state.mermaid_editor = example_models[selected_example]
                st.rerun()

        st.divider()

        # Upload model
        st.subheader("Upload Model")
        uploaded_file = st.file_uploader("Choose a .mmd file", type=["mmd", "mermaid"])
        if uploaded_file is not None:
            content = uploaded_file.read().decode("utf-8")
            st.session_state.mermaid_input = content
            st.session_state.mermaid_editor = content
            st.success(f"Loaded {uploaded_file.name}")

        st.divider()

        # Submit new model
        st.subheader("Submit Model")
        st.markdown("Share your model with the community")
        new_model_name = st.text_input("Model name")
        if st.button("Submit") and new_model_name:
            st.info("Submission feature coming soon!")

    # Initialize session state
    if 'mermaid_input' not in st.session_state:
        if example_models:
            st.session_state.mermaid_input = list(example_models.values())[0]
        else:
            st.session_state.mermaid_input = ""

    # Main content area

    # Section 1: Model Definition
    with st.expander("📝 Model Definition", expanded=True):
        st.markdown("Edit the Mermaid diagram below to define your model")

        col1, col2 = st.columns([1, 2])

        with col1:
            st.subheader("Mermaid Text")
            mermaid_text = st.text_area(
                "Enter Mermaid diagram",
                value=st.session_state.mermaid_input,
                height=400,
                key="mermaid_editor",
                label_visibility="collapsed"
            )

            if st.button("🔄 Refresh Preview"):
                st.session_state.mermaid_input = mermaid_text

        with col2:
            st.subheader("Partial Diagram")
            if mermaid_text.strip():
                # Render using streamlit-mermaid
                st_mermaid(mermaid_text, height=600)
            else:
                st.info("Enter a Mermaid diagram to see preview")

    # Section 2: Complete Model
    with st.expander("📊 Complete Model", expanded=False):
        if mermaid_text.strip():
            try:
                # Parse the diagram
                model, partial_spec = parse_dbt_diagram(mermaid_text)

                # Show overview
                st.markdown(format_model_overview(model))

                st.divider()

                # Show complete Index diagram
                st.subheader("Complete Index Structure")
                index_diagram = serialize_index(model, partial_spec, mode="complete")
                # Use full width for complete diagram
                st_mermaid(index_diagram, height=800)

            except Exception as e:
                st.error(f"Failed to parse model: {str(e)}")
        else:
            st.info("Enter a Mermaid diagram in the Model Definition section")

    # Section 3: Responsibility Analysis
    with st.expander("🧠 Responsibility Analysis", expanded=False):
        if mermaid_text.strip():
            st.markdown("""Analyze responsibility for outcomes using various operators.

All formulae will be analysed at m/h1.

**Note:** Analysis on Streamlit Cloud may be slow due to resource constraints.
For faster results, download the OWL file and run locally using `analyze_owl.py`.""")

            col1, col2 = st.columns([1, 1])

            with col1:
                if st.button("▶️ Run Analysis (Cloud)"):
                    with st.spinner("Running responsibility analysis..."):
                        try:
                            # Parse model
                            model, partial_spec = parse_dbt_diagram(mermaid_text)

                            # Get result prop and eval history
                            result_prop = partial_spec.get("result", "q")
                            eval_point = partial_spec.get("evaluation_point", "m/h1")
                            eval_history = eval_point.split("/")[1] if "/" in eval_point else "h1"

                            # Run analysis
                            satisfied_query_ids = run_responsibility_analysis(model, result_prop, eval_history)

                            if satisfied_query_ids is not None:
                                st.success(f"Analysis complete! Found {len(satisfied_query_ids)} satisfied queries")

                                # Show results table
                                results_md = format_results_table(model, satisfied_query_ids, result_prop)
                                st.markdown(results_md)

                        except Exception as e:
                            st.error(f"Analysis failed: {str(e)}")

            with col2:
                st.markdown("**Download for Local Analysis:**")

                # Download analyzer script
                analyzer_path = Path(__file__).parent.parent / "analyze_owl.py"
                if analyzer_path.exists():
                    with open(analyzer_path, 'r') as f:
                        analyzer_content = f.read()
                    st.download_button(
                        label="📥 Download Analyzer Script",
                        data=analyzer_content,
                        file_name="analyze_owl.py",
                        mime="text/x-python",
                        help="Standalone Python script (no dependencies)"
                    )

                if st.button("📥 Generate OWL File"):
                    try:
                        # Parse model
                        model, partial_spec = parse_dbt_diagram(mermaid_text)

                        # Get result prop and eval history
                        result_prop = partial_spec.get("result", "q")
                        eval_point = partial_spec.get("evaluation_point", "m/h1")
                        eval_history = eval_point.split("/")[1] if "/" in eval_point else "h1"

                        # Generate queries
                        resp_config = ResponsibilityConfig(
                            target_proposition=result_prop,
                            agents="all",
                            groups="all",
                            responsibility_types=["pres", "sres", "res", "dxstit", "but", "ness"],
                            history=eval_history
                        )
                        model.responsibility_config = resp_config
                        queries = generate_queries(model)
                        model.queries.extend(queries)
                        model = parse_queries(model)
                        model = expand_queries(model, evaluation_history=eval_history)

                        # Serialize to OWL
                        strategy = EquivFullCardinalityStrategy()
                        serializer = OWLIndexNewExpanderSerializer(model, strategy=strategy)
                        owl_output = serializer.serialize()

                        # Offer download
                        st.download_button(
                            label="⬇️ Download OWL File",
                            data=owl_output,
                            file_name="model.owl",
                            mime="application/rdf+xml",
                            help="Download this file and analyze locally with analyze_owl.py",
                            key="download_owl"
                        )

                        st.success(f"OWL file ready ({len(owl_output):,} bytes)")
                        st.code("python analyze_owl.py model.owl", language="bash")

                    except Exception as e:
                        st.error(f"OWL generation failed: {str(e)}")
        else:
            st.info("Enter a Mermaid diagram in the Model Definition section")


if __name__ == "__main__":
    main()
