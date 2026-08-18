"""
ALOn Model Explorer — main page.
"""

import sys
from pathlib import Path

import streamlit as st
from streamlit_mermaid import st_mermaid

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import (
    copy_button,
    format_layered_model_overview,
    format_layered_results_table,
    konclude_path,
    load_example_models,
    parse_model,
    run_analysis_datalog_layered,
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

            st.markdown(f"**Temporal depth**: {model.depth()}")
            st.markdown(format_layered_model_overview(model))

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
            _result_prop_default = _model_ra.target_proposition
            _named_histories = sorted(_model_ra.histories.keys())
        except Exception:
            _model_ra = None
            _result_prop_default = "q"
            _named_histories = ["h1"]

        konclude_bin = konclude_path()
        if konclude_bin:
            backend = st.radio("Reasoner", ["pyDatalog", "Konclude (OWL)"], horizontal=True)
            use_konclude = backend == "Konclude (OWL)"
        else:
            use_konclude = False

        _ness_default = _partial_spec_ra.get("ness_empty_sufficient", True) if _model_ra else True
        ness_empty_sufficient = st.checkbox(
            "NESS: empty set counts as sufficient (original semantics)",
            value=_ness_default,
            help="When checked, q-inevitability ([]Xq) blocks NESS — matching the original "
                 "semantics. Uncheck to require only non-empty proper subsets, so a singleton "
                 "action is trivially minimal regardless of inevitability.",
        )

        if st.button("▶️ Run Analysis"):
            with st.spinner("Running responsibility analysis..."):
                try:
                    model, _ = parse_model(mermaid_text)
                    run_layered = run_analysis_konclude_layered if use_konclude else run_analysis_datalog_layered
                    satisfied_query_ids = run_layered(model, ness_empty_sufficient=ness_empty_sufficient)
                    if satisfied_query_ids is not None:
                        st.success(f"Analysis complete! Found {len(satisfied_query_ids)} satisfied queries")
                        results_md = format_layered_results_table(model, satisfied_query_ids)
                        col_r, col_rb, col_rl = st.columns([7, 1, 1])
                        with col_r:
                            st.markdown(results_md)
                        with col_rb:
                            copy_button(results_md, "📋 Copy")
                        with col_rl:
                            copy_button(format_layered_results_table(model, satisfied_query_ids, fmt="latex"), "⎇ LaTeX")
                except Exception as e:
                    st.error(f"Analysis failed: {e}")


# ── Section 4: Direct Formula Evaluation ─────────────────────────────────────

with st.expander("Formula Evaluation", expanded=True):
    if not mermaid_text.strip():
        st.info("Enter a Mermaid diagram in the Model Definition section")
    else:
        try:
            _model_ev, _partial_spec_ev = parse_model(mermaid_text)
        except Exception:
            _model_ev = None
            _partial_spec_ev = {}

        _yaml_evaluate = (_partial_spec_ev or {}).get("evaluate", [])

        if not _yaml_evaluate:
            st.info("Add an `evaluate` block to your frontmatter to check formulas directly at an index.\n\n"
                    "Example:\n```yaml\nevaluate:\n  - - m/h1\n    - \"do(sd1) [+]-> q\"\n```")
        else:
            if st.button("▶️ Evaluate", key="ev_run"):
                with st.spinner("Evaluating…"):
                    try:
                        from alo_docs._runner import _run_evaluate, format_evaluate_results
                        _m_ev, _partial_spec_ev2 = parse_model(mermaid_text)
                        _m_ev, _sat_ev, _pts_ev = _run_evaluate(_m_ev, _partial_spec_ev2)
                        _ev_md = format_evaluate_results(_m_ev, _sat_ev, _pts_ev)
                        st.session_state["ev_result_md"] = _ev_md
                    except Exception as _e:
                        st.error(f"Evaluation failed: {_e}")
                        import traceback; st.code(traceback.format_exc())

            if st.session_state.get("ev_result_md"):
                _col_ev, _col_evb = st.columns([8, 1])
                with _col_ev:
                    st.markdown(st.session_state["ev_result_md"])
                with _col_evb:
                    copy_button(st.session_state["ev_result_md"], "📋 Copy")
