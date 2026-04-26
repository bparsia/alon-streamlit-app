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

from alo_translator.model.core import LayeredALOModel

from utils import (
    copy_button,
    format_model_overview,
    format_history_table_md,
    format_results_table,
    format_layered_model_overview,
    format_layered_results_table,
    konclude_path,
    load_example_models,
    parse_model,
    run_analysis_datalog,
    run_analysis_datalog_layered,
    run_analysis_konclude,
    run_analysis_konclude_layered,
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
        if selected and selected != st.session_state.get("_loaded_model"):
            st.session_state.mermaid_input = example_models[selected]
            st.session_state.mermaid_editor = example_models[selected]
            st.session_state._loaded_model = selected
            st.query_params["model"] = selected
        elif not selected:
            st.session_state.pop("_loaded_model", None)
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
            model, partial_spec = parse_model(mermaid_text)

            if isinstance(model, LayeredALOModel):
                st.markdown(f"**Temporal depth**: {model.depth()} (TD>1 model)")
                st.markdown(format_layered_model_overview(model))
            else:
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
        st.markdown("Analyse responsibility for outcomes using various operators.")

        # Parse model early to populate dropdowns (best-effort — errors handled below)
        try:
            _model_ra, _partial_spec_ra = parse_model(mermaid_text)
            _is_layered_ra = isinstance(_model_ra, LayeredALOModel)
            if _is_layered_ra:
                _result_prop_default = _model_ra.target_proposition
                _named_histories = sorted(_model_ra.histories.keys())
            else:
                _result_prop_default = _partial_spec_ra.get("result", "q")
                _named_histories = sorted(_model_ra.named_histories.keys())
        except Exception:
            _model_ra = None
            _is_layered_ra = False
            _result_prop_default = "q"
            _named_histories = ["h1"]

        st.markdown(f"Outcome proposition: `{_result_prop_default}`")

        if _is_layered_ra:
            st.info(f"TD>1 model (depth {_model_ra.depth()}). "
                    f"Evaluating at `{_model_ra.evaluation_moment}/{_model_ra.evaluation_history}`.")
            _eval_history_sel = _model_ra.evaluation_history
        else:
            # History selection (dropdown only when multiple named histories exist)
            if len(_named_histories) > 1:
                _eval_history_sel = st.selectbox(
                    "Evaluate at history",
                    _named_histories,
                    index=0,
                )
            else:
                _eval_history_sel = _named_histories[0] if _named_histories else "h1"
                st.markdown(f"Formulae are evaluated at m/{_eval_history_sel}.")

        konclude_bin = konclude_path()
        if konclude_bin:
            backend = st.radio("Reasoner", ["pyDatalog", "Konclude (OWL)"], horizontal=True)
            use_konclude = backend == "Konclude (OWL)"
        else:
            use_konclude = False

        if st.button("▶️ Run Analysis"):
            with st.spinner("Running responsibility analysis..."):
                try:
                    model, partial_spec = parse_model(mermaid_text)
                    is_layered = isinstance(model, LayeredALOModel)

                    if is_layered:
                        run_layered = run_analysis_konclude_layered if use_konclude else run_analysis_datalog_layered
                        satisfied_query_ids = run_layered(model)
                        if satisfied_query_ids is not None:
                            st.success(f"Analysis complete! Found {len(satisfied_query_ids)} satisfied queries")
                            results_md = format_layered_results_table(model, satisfied_query_ids)
                            col_r, col_rb = st.columns([8, 1])
                            with col_r:
                                st.markdown(results_md)
                            with col_rb:
                                copy_button(results_md, "📋 Copy")
                    else:
                        result_prop  = partial_spec.get("result", "q")
                        eval_history = _eval_history_sel

                        run = run_analysis_konclude if use_konclude else run_analysis_datalog
                        satisfied_query_ids = run(model, result_prop, eval_history)

                        if satisfied_query_ids is not None:
                            st.success(
                                f"Analysis complete! "
                                f"Found {len(satisfied_query_ids)} satisfied queries"
                            )
                            with st.expander("🔍 Debug", expanded=False):
                                st.write(f"result_prop: `{result_prop}`")
                                st.write(f"eval_history: `{eval_history}`")
                                st.write(f"model.queries count: {len(model.queries)}")
                                if model.queries:
                                    st.write("Sample query IDs:", [q.query_id for q in model.queries[:5]])
                                st.write(f"satisfied_query_ids: {sorted(satisfied_query_ids)[:5]}")
                            results_md = format_results_table(model, satisfied_query_ids, result_prop)
                            col_r, col_rb = st.columns([8, 1])
                            with col_r:
                                st.markdown(results_md)
                            with col_rb:
                                copy_button(results_md, "📋 Copy")

                except Exception as e:
                    st.error(f"Analysis failed: {e}")
