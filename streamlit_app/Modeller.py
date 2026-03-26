"""
ALOn Model Explorer — main page.
"""

import sys
from pathlib import Path

import streamlit as st
from streamlit_mermaid import st_mermaid

sys.path.insert(0, str(Path(__file__).parent.parent))

from alo_translator.parsers.dbt_parser import parse_dbt_diagram
from alo_translator.serializers.index_mermaid import serialize_index
from alo_translator.serializers.dbt_mermaid import serialize_dbt

from utils import (
    copy_button,
    format_model_overview,
    format_history_table_md,
    format_results_table,
    konclude_path,
    load_example_models,
    run_analysis_datalog,
    run_analysis_konclude,
)

st.set_page_config(
    page_title="ALOn Model Explorer",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .stTextArea textarea { font-family: monospace; font-size: 12px; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar — model repository
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📚 Model Repository")

    example_models = load_example_models()
    if example_models:
        st.subheader("Example Models")

        # Pre-select from URL query param if present
        url_model = st.query_params.get("model", "")
        default_idx = ([""] + list(example_models.keys())).index(url_model) \
            if url_model in example_models else 0

        selected = st.selectbox(
            "Load example",
            [""] + list(example_models.keys()),
            index=default_idx,
            format_func=lambda x: "Select an example..." if x == "" else x,
        )
        if selected:
            st.session_state.mermaid_input = example_models[selected]
            st.session_state.mermaid_editor = example_models[selected]
            st.query_params["model"] = selected
        else:
            st.query_params.pop("model", None)

    st.divider()

    st.subheader("Upload Model")
    uploaded = st.file_uploader("Choose a .mmd file", type=["mmd", "mermaid"])
    if uploaded:
        content = uploaded.read().decode("utf-8")
        st.session_state.mermaid_input = content
        st.session_state.mermaid_editor = content
        st.success(f"Loaded {uploaded.name}")

    st.divider()

    st.subheader("Submit Model")
    st.markdown("Share your model with the community")
    if st.text_input("Model name") and st.button("Submit"):
        st.info("Submission feature coming soon!")


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "mermaid_input" not in st.session_state:
    st.session_state.mermaid_input = list(example_models.values())[0] if example_models else ""


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("ALOn Model Explorer")
st.markdown(
    "Interactive tool for editing, visualizing, and reasoning over ALOn models"
)
st.markdown("""
You may load or enter either a Discrete Branching Time or an Index style model.
The model can also be *partially* specified:

1. You can omit some complete group actions (and their associated histories).
   You must always designate h1 (the evaluation history); additional ones
   should be consecutively numbered.
2. If a successor moment is omitted, it defaults to the negation of the target outcome.
""")

mermaid_text = st.session_state.mermaid_input  # may be updated below


# ── Section 1: Model Definition ──────────────────────────────────────────────

with st.expander("Model Definition", expanded=True):
    st.markdown("Edit the Mermaid diagram below to define your model")
    col_edit, col_preview = st.columns([1, 2])

    with col_edit:
        st.subheader("Mermaid Text")
        mermaid_text = st.text_area(
            "Enter Mermaid diagram",
            value=st.session_state.mermaid_input,
            height=400,
            key="mermaid_editor",
            label_visibility="collapsed",
        )
        if st.button("🔄 Refresh Preview"):
            st.session_state.mermaid_input = mermaid_text

    with col_preview:
        st.subheader("Partial Diagram")
        if mermaid_text.strip():
            st_mermaid(mermaid_text, height=600)
        else:
            st.info("Enter a Mermaid diagram to see preview")


# ── Section 2: Complete Model ─────────────────────────────────────────────────

with st.expander("Complete Model", expanded=True):
    if not mermaid_text.strip():
        st.info("Enter a Mermaid diagram in the Model Definition section")
    else:
        try:
            model, partial_spec = parse_dbt_diagram(mermaid_text)

            st.markdown(format_model_overview(model))
            st.divider()

            # Index diagram
            index_diagram = serialize_index(model, partial_spec, mode="complete")
            col_hdr, col_btn = st.columns([6, 1])
            with col_hdr:
                st.subheader("Complete Index Structure")
            with col_btn:
                copy_button(index_diagram, "📋 Index")
            st_mermaid(index_diagram, height=800)

            # History / export copy buttons
            col_hdr2, col_btn2, col_btn3 = st.columns([6, 1, 1])
            with col_hdr2:
                st.subheader("Histories")
            with col_btn2:
                copy_button(format_history_table_md(model), "📋 Table")
            with col_btn3:
                copy_button(serialize_dbt(model, partial_spec, mode="complete"), "📋 DBT")

        except Exception as e:
            st.error(f"Failed to parse model: {e}")


# ── Section 3: Responsibility Analysis ───────────────────────────────────────

with st.expander("Responsibility Analysis", expanded=True):
    if not mermaid_text.strip():
        st.info("Enter a Mermaid diagram in the Model Definition section")
    else:
        st.markdown("Analyse responsibility for outcomes using various operators.\n\n"
                    "All formulae are evaluated at m/h1.")

        konclude_bin = konclude_path()
        if konclude_bin:
            backend = st.radio("Reasoner", ["pyDatalog", "Konclude (OWL)"], horizontal=True)
            use_konclude = backend == "Konclude (OWL)"
        else:
            use_konclude = False

        if st.button("▶️ Run Analysis"):
            with st.spinner("Running responsibility analysis..."):
                try:
                    model, partial_spec = parse_dbt_diagram(mermaid_text)

                    result_prop  = partial_spec.get("result", "q")
                    eval_point   = partial_spec.get("evaluation_point", "m/h1")
                    eval_history = eval_point.split("/")[1] if "/" in eval_point else "h1"

                    run = run_analysis_konclude if use_konclude else run_analysis_datalog
                    satisfied_query_ids = run(model, result_prop, eval_history)

                    if satisfied_query_ids is not None:
                        st.success(
                            f"Analysis complete! "
                            f"Found {len(satisfied_query_ids)} satisfied queries"
                        )
                        results_md = format_results_table(model, satisfied_query_ids, result_prop)
                        col_r, col_rb = st.columns([8, 1])
                        with col_r:
                            st.markdown(results_md)
                        with col_rb:
                            copy_button(results_md, "📋 Copy")

                except Exception as e:
                    st.error(f"Analysis failed: {e}")
