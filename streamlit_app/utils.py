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
from alo_translator.parsers.expander_transformer import ExpanderTransformer
from alo_translator.query_generation import ResponsibilityConfig, generate_queries
from alo_translator.serializers.datalog import DatalogIndexSerializer
from alo_translator.serializers.sparql import FormulaToSPARQL
from alo_translator.model.core import ALOModel, Query

def _sanitize_id(s: str) -> str:
    """Convert a formula string to a safe query-ID suffix (mirrors query_generation._sanitize_id)."""
    result = re.sub(r'[(){}\[\],: ~]', '_', s)
    result = re.sub(r'_+', '_', result)
    return result.strip('_')


# Konclude imports — only available when running locally with the binary present
try:
    from alo_translator.serializers.owl import OWLSerializer
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


def analysis_button(key: str, model, result_prop: str = "q", eval_point: str = "m/h1",
                    label: str = "▶️ Run Analysis", show_legend: bool = True) -> None:
    """
    Render a self-contained analysis button that persists results across reruns.

    Args:
        key: Unique session_state key for this analysis (e.g. "tut_analysis_1").
        model: Parsed ALOn model.
        result_prop: Outcome proposition to evaluate (default "q").
        eval_point: "moment/history" to evaluate at (default "m/h1").
        label: Button label text.
    """
    if st.button(label, key=f"btn_{key}"):
        with st.spinner("Running…"):
            eval_history = eval_point.split("/")[1] if "/" in eval_point else "h1"
            satisfied    = run_analysis_datalog(model, result_prop, eval_history)
            if satisfied is not None:
                # Store the rendered markdown — model.queries won't survive the rerun
                st.session_state[key] = format_results_table(model, satisfied, result_prop,
                                                              show_legend=show_legend,
                                                              eval_point=eval_point)

    if key in st.session_state:
        results_md = st.session_state[key]
        col_r, col_rb = st.columns([8, 1])
        with col_r:
            st.markdown(results_md)
        with col_rb:
            copy_button(results_md, "📋 Copy")


def _validate_formula(formula: str) -> Optional[str]:
    """Return an error message if *formula* is not a valid ALOn formula, else None."""
    from alo_translator.parsers.formula_parser import parse_formula
    try:
        parse_formula(formula)
        return None
    except Exception as e:
        return str(e).splitlines()[0]  # First line of Lark error is most informative


def run_analysis_datalog(model, result_prop: str, eval_history: str,
                         ness_empty_sufficient: bool = True) -> Optional[Set[str]]:
    """Run responsibility analysis using pyDatalog. Returns satisfied query IDs."""
    err = _validate_formula(result_prop)
    if err:
        st.error(f"Invalid outcome proposition `{result_prop}`: {err}")
        return None
    try:
        model = setup_queries(model, result_prop, eval_history)
        serializer = DatalogIndexSerializer(model, evaluation_history=eval_history,
                                            ness_empty_sufficient=ness_empty_sufficient)
        results = serializer.evaluate()
        return {qid for qid, r in results.items() if r.get("result")}
    except Exception as e:
        st.error(f"Analysis error: {e}")
        return None


def parse_model(mermaid_text: str) -> Tuple[ALOModel, Dict]:
    """Parse a Mermaid diagram and return (model, partial_spec)."""
    return parse_dbt_diagram(mermaid_text), {}


def _target_x_count(model: ALOModel) -> int:
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
    return 1


def _outcome_formula(model: ALOModel) -> str:
    """Return the outcome formula for display (e.g. 'Xdo(sd1)' or 'Xq')."""
    x_count = _target_x_count(model)
    return 'X' * x_count + model.target_proposition


def _operator_formula(model: ALOModel) -> str:
    """Return the formula to pass to responsibility operators.

    All operators (pres/sres/res/but/ness) internally add one X step,
    so the formula should have one fewer X than the raw target depth.
    """
    x_count = _target_x_count(model)
    inner_x = max(0, x_count - 1)
    return 'X' * inner_x + model.target_proposition


def setup_layered_queries(model: ALOModel) -> ALOModel:
    """Attach responsibility queries to a ALOModel for analysis."""
    from alo_translator.query_generation import _sanitize_id
    model.responsibility_config = ResponsibilityConfig(
        target_proposition=model.target_proposition,
        agents="all",
        groups="all",
        responsibility_types=["pres", "sres", "res", "dxstit", "but", "ness"],
        history=model.evaluation_history,
        moment=model.evaluation_moment,
    )
    queries = generate_queries(model)
    # Scope each query ID with emom/ehist/target so multiple eval points don't collide
    scope = _sanitize_id(f"{model.evaluation_moment}_{model.evaluation_history}_{model.target_proposition}")
    for q in queries:
        if q.query_id:
            q.query_id = f"{q.query_id}_{scope}"
    # Add outcome formula as a direct query so display can read holds from results.
    # Wrap in X so it's evaluated at the successor of emom (where outcomes live).
    from alo_translator.model.core import Query
    outcome_qid = f"outcome_{scope}"
    queries.append(Query(formula_string=f"X{model.target_proposition}", query_id=outcome_qid))
    model.queries = queries
    model.responsibility_config = None  # prevent parse_queries from re-generating
    return parse_queries(model)


def run_analysis_datalog_layered(model: ALOModel,
                                  ness_empty_sufficient: bool = True) -> Optional[Set[str]]:
    """Run responsibility analysis on a ALOModel using pyDatalog.

    If model.evaluations is set, runs each (moment, history, target) separately
    and unions the satisfied query IDs. Accumulates all queries on model.queries
    so format_layered_results_table can display each section correctly.
    """
    try:
        eval_points = model.require_evaluations()
        all_satisfied: Set[str] = set()
        all_queries = []
        for emom, ehist, etgt in eval_points:
            model.evaluation_moment = emom
            model.evaluation_history = ehist
            model.target_proposition = etgt
            model.queries = []
            model = setup_layered_queries(model)
            all_queries.extend(model.queries)
            serializer = DatalogIndexSerializer(model,
                                                       evaluation_history=ehist,
                                                       evaluation_moment=emom,
                                                       ness_empty_sufficient=ness_empty_sufficient)
            results = serializer.evaluate()
            all_satisfied.update(qid for qid, r in results.items() if r.get("result"))
        model.queries = all_queries
        return all_satisfied
    except Exception as e:
        st.error(f"Analysis error: {e}")
        return None


def run_analysis_konclude_layered(model: ALOModel,
                                   ness_empty_sufficient: bool = True) -> Optional[Set[str]]:
    """Run responsibility analysis on a ALOModel using Konclude (OWL).

    Mirrors run_analysis_datalog_layered but uses OWLSerializer
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

        eval_points = model.require_evaluations()
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
            serializer = OWLSerializer(
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


def run_analysis_konclude_sparql_layered(model: ALOModel,
                                          ness_empty_sufficient: bool = True) -> Optional[Set[str]]:
    """Run responsibility analysis on a ALOModel using Konclude's SPARQL
    mode (MINUS-based negation), instead of OWL SubClassOf-injection +
    full realization.

    Mirrors run_analysis_konclude_layered's shape and per-eval-point loop.
    The OWL ontology (ABox: indices/succ/same_moment/actions/props, TBox
    structural axioms) is built identically via the same OWLSerializer/
    EquivFullCardinalityStrategy -- only the query-answering step differs:
    instead of injecting SubClassOf axioms per query and running full
    REALISATION, each query's expanded formula is compiled to a single
    SPARQL SELECT query (FormulaToSPARQL), and ALL of a given eval point's
    queries are run against one warm KoncludeSparqlServer instance
    (ontology loaded/classified once, not once per query -- see that
    class's docstring for why: the naive one-`sparqlfile`-subprocess-
    per-query approach did not finish within 10 minutes on the real
    3.5.mmd model's 90 queries, versus 16.65s through a warm server,
    faster than the 32.1s OWL/realization path on the same model).

    See docs/sparql_serializer.md for the design this implements.
    """
    try:
        from alo_translator.serializers.index_strategies import EquivFullCardinalityStrategy
        from alo_translator.reasoners.konclude import KoncludeSparqlServer

        bin_path = konclude_path()
        if bin_path is None:
            st.error("Konclude binary not found.")
            return None

        eval_points = model.require_evaluations()
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
            serializer = OWLSerializer(
                model,
                evaluation_moment=emom,
                evaluation_history=ehist,
                strategy=strategy,
            )
            # structural_only: SPARQL compiles formula logic directly via
            # FormulaToSPARQL (MINUS/UNION), so the ~300+ per-query
            # SubClassOf expansion axioms serialize() would otherwise
            # inject are unused dead weight here -- and expensive dead
            # weight: they're exactly what a DL reasoner's classification
            # step has to process, and measured on 3.5.mmd this made the
            # first SPARQL query against a freshly-started server take
            # ~30s before this was split out (see
            # OWLSerializer.serialize_structural_only's docstring).
            owl_output = serializer.serialize_structural_only()

            with tempfile.NamedTemporaryFile(mode="w", suffix=".owl", delete=False) as f:
                f.write(owl_output)
                owl_path = Path(f.name)

            try:
                eval_idx = f"{emom}_{ehist}"

                with KoncludeSparqlServer(bin_path, owl_path) as server:
                    for query in model.queries:
                        if not query.query_id:
                            continue
                        full_query = compile_query_to_sparql(
                            query, model, serializer.parser,
                            evaluation_moment=emom, evaluation_history=ehist,
                            ness_empty_sufficient=ness_empty_sufficient,
                        )
                        if full_query is None:
                            continue
                        bound = server.query(full_query)
                        if eval_idx in bound:
                            all_satisfied.add(query.query_id)
            finally:
                owl_path.unlink()

        model.queries = all_queries
        return all_satisfied
    except Exception as e:
        st.error(f"Konclude SPARQL analysis error: {e}")
        return None


def compile_query_to_sparql(query, model: ALOModel, parser, evaluation_moment: str,
                             evaluation_history: str, ness_empty_sufficient: bool = True) -> Optional[str]:
    """Compile a single Query's formula_string to a full, self-contained
    "PREFIX ... SELECT ?idx0 WHERE {...}" SPARQL query string, ready to
    run against a KoncludeSparqlServer.

    Each call gets its own fresh ExpanderTransformer/FormulaToSPARQL pass
    (no shared fN helper classes between queries, no dependency on OWL
    SubClassOf axioms for sub-formulas -- deliberate per user direction,
    simpler and more robust than a stateful multi-query pipeline sharing
    intermediate results across HTTP calls). This does re-expand shared
    sub-formulas (e.g. "expected_result" appears inside pres/sres/res)
    once per top-level query rather than once per model -- acceptable
    duplication given ALOn's real formulas don't nest deeply (see
    docs/sparql_serializer.md).

    Returns None if the query's top-level formula never reaches a real
    SPARQL fragment (currently: only if FormulaToSPARQL produced nothing
    for the synthesized top-level name, which is not expected to happen
    in practice but is handled rather than assumed impossible).

    Shared by run_analysis_konclude_sparql_layered (this module) and
    papers/2026Fear/generate_tables.py's performance-timing loop --
    factored out after a real bug (isabella.mmd's action-valued
    target_proposition produces a compound "outcome" formula like
    "Xdo(sd1)", not a bare identifier) needed the identical fix in both
    call sites; keeping one implementation avoids that happening again.
    """
    expander = ExpanderTransformer(
        parser, model,
        evaluation_moment=evaluation_moment, evaluation_history=evaluation_history,
        ness_empty_sufficient=ness_empty_sufficient,
    )
    top_name = str(expander.transform(parser.parse(query.formula_string)))
    expansions = _fN_expansion_map(expander.axioms)
    # Not every top-level query goes through ExpanderTransformer._name_for
    # -- primitive constructs (e.g. the bare "outcome" query) are
    # returned as an already-compiled/primitive string directly, with no
    # entry in .axioms to look up (nothing to expand: it's already
    # primitive). Only inline when top_name actually names something.
    # This primitive string can itself be COMPOUND (e.g. "Xdo(sd1)" when
    # the model's target_proposition is an action, not a bare prop --
    # confirmed via isabella.mmd) rather than a simple identifier -- using
    # it directly as the "=> name" RHS below would be invalid ALOn syntax
    # (axiom names must be plain identifiers), so a synthetic name is
    # minted whenever top_name isn't already fN-shaped.
    top_definition = expansions.get(top_name, top_name)
    inlined = _inline_fN_references(top_definition, expansions)

    axiom_name = top_name if re.fullmatch(r"f\d+", top_name) else "sparql_top"

    formula_to_sparql = FormulaToSPARQL(name_to_formula=expander.name_to_formula)
    formula_to_sparql.transform(parser.parse(f"({inlined}) => {axiom_name}"))
    sparql_text = formula_to_sparql.queries.get(axiom_name)
    if sparql_text is None:
        return None
    return (
        "PREFIX alon: <http://www.semanticweb.org/alon#>\n"
        "PREFIX owl: <http://www.w3.org/2002/07/owl#>\n"
        f"{sparql_text}"
    )


def _fN_expansion_map(axioms) -> Dict[str, str]:
    """Build a {name: expansion} map from an ExpanderTransformer's
    axioms (each a "<expansion> => <name>" string).

    NOT the same as ExpanderTransformer.name_to_formula, which maps each
    name to the ORIGINAL surface formula it names (e.g. "f1" -> "[1
    pres]q") -- that's for OWL annotations/documentation, not the actual
    derivation. The real expansion (what f1 is actually defined as, in
    terms of primitive/other fN constructs) only exists in .axioms.
    """
    expansions: Dict[str, str] = {}
    for axiom in axioms:
        if "=>" not in axiom:
            continue
        lhs, _, rhs = axiom.rpartition("=>")
        expansions[rhs.strip()] = lhs.strip()
    return expansions


def _inline_fN_references(formula_string: str, expansions: Dict[str, str]) -> str:
    """Recursively substitute every fN helper-name reference in
    formula_string with its own defining EXPANSION (parenthesized, from
    `expansions`, see `_fN_expansion_map`), until no fN references remain.

    ExpanderTransformer._name_for caches each distinct sub-formula under
    a systematic fN name (f1, f2, ...) and reuses that name wherever the
    same sub-formula recurs -- this is what OWL's SubClassOf-per-fN-class
    mechanism exists to materialize. FormulaToSPARQL has no equivalent
    (no OWL classes for the SPARQL path, see
    OWLSerializer.serialize_structural_only), so every fN reference must
    be inlined back into the formula text before compiling to SPARQL, or
    FormulaToSPARQL.prop() would wrongly treat "fN" as a bare atomic
    proposition (`?idx a alon:fN .`) with no defining axiom to back it.

    Whole-token matching only (word boundaries) -- fN names never appear
    as a substring of anything else in these formula strings (query IDs
    use a 'q' prefix specifically to avoid collision, see
    ExpanderTransformer._name_for's comment).
    """
    pattern = re.compile(r'\bf\d+\b')

    def expand_once(s: str) -> str:
        return pattern.sub(lambda m: f"({expansions[m.group(0)]})" if m.group(0) in expansions else m.group(0), s)

    # Fixed-point iteration: each pass can introduce new fN references
    # (from a just-inlined definition), stop once a pass changes nothing.
    # Guard against a pathological/cyclic definition with a hard cap --
    # not expected in practice (expansion axioms are acyclic by
    # construction) but a silent infinite loop would be worse than a
    # loud one here.
    current = formula_string
    for _ in range(1000):
        expanded = expand_once(current)
        if expanded == current:
            return current
        current = expanded
    raise RuntimeError(f"fN inlining did not converge after 1000 passes: {formula_string!r}")


def format_layered_model_overview(model: ALOModel) -> str:
    """Format a ALOModel overview as markdown."""
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


def _cga_str(actions: Dict[str, str], aliases: Dict[str, str]) -> str:
    """Format a {agent: action_type} dict as a CGA string like {masd3, sd1, ss2}."""
    parts = sorted(f"{atype}{agent}" for agent, atype in actions.items())
    return "{" + ", ".join(parts) + "}"


def _outcome_index(model: ALOModel, ehist: str, etgt: str, emom: str = None):
    """Return (holds: bool, index: str) for the target at the next moment after emom.

    Outcomes are always evaluated at the successor of the evaluation moment (Xφ).
    If emom is not given, falls back to the first non-leaf moment on the path.
    """
    hp = model.histories.get(ehist)
    if hp is None:
        return False, "?"

    # Find the successor of emom on this history's path
    if emom is not None and emom in hp.path:
        idx = hp.path.index(emom)
        if idx + 1 < len(hp.path):
            next_mom = hp.path[idx + 1]
        else:
            return False, f"{emom}/{ehist}"
    else:
        # fallback: first transition
        next_mom = hp.path[1] if len(hp.path) > 1 else hp.path[0]

    next_node = model.moments.get(next_mom)
    next_index = f"{next_mom}/{ehist}"

    def _parse_do(action_str: str):
        """Parse 'sd1' -> (atype, agent) or None."""
        m = re.match(r"^([a-zA-Z]+)(\d+)$", action_str)
        return (m.group(1), m.group(2)) if m else None

    def _do_at(moment: str, h: str, action_str: str) -> bool:
        parsed = _parse_do(action_str)
        if not parsed:
            return False
        atype, agent = parsed
        return model.histories[h].actions_at.get(moment, {}).get(agent) == atype

    def _same_moment_histories(moment: str):
        return [h for h in model.histories if moment in model.histories[h].path]

    if etgt.startswith("do("):
        holds = _do_at(next_mom, ehist, etgt[3:-1])
    elif etgt.startswith("[]do("):
        inner = etgt[5:-1]
        same = _same_moment_histories(next_mom)
        holds = bool(same) and all(_do_at(next_mom, h, inner) for h in same)
    elif etgt.startswith("<>do("):
        inner = etgt[5:-1]
        same = _same_moment_histories(next_mom)
        holds = any(_do_at(next_mom, h, inner) for h in same)
    else:
        holds = next_node is not None and etgt in next_node.propositions
    return holds, next_index


def _section_header_layered(model: ALOModel, emom: str, ehist: str, etgt: str,
                             satisfied_ids: Set[str] = None) -> str:
    from alo_translator.query_generation import _sanitize_id
    aliases = model.aliases
    hp = model.histories.get(ehist)
    cga_dict = hp.actions_at.get(emom, {}) if hp else {}
    cga = _cga_str(cga_dict, aliases) if cga_dict else "{}"
    scope = _sanitize_id(f"{emom}_{ehist}_{etgt}")
    outcome_qid = f"outcome_{scope}"
    if satisfied_ids is not None:
        holds = outcome_qid in satisfied_ids
    else:
        _, index = _outcome_index(model, ehist, etgt, emom)
        holds = False  # fallback: unknown
    _, index = _outcome_index(model, ehist, etgt, emom)
    tgt_desc = aliases.get(etgt, etgt)
    holds_str = "holds" if holds else "does not hold"
    outcome_label = f"`{etgt}`" + (f" ({tgt_desc})" if tgt_desc != etgt else "")
    return (
        f"**At:** `{emom}/{ehist}`  \n"
        f"**CGA:** `{cga}`  \n"
        f"**Outcome:** {outcome_label} — {holds_str} at `{index}`"
    )


def format_layered_results_table(model: ALOModel, satisfied_ids: Set[str],
                                  fmt: str = "markdown") -> str:
    """Format ALOModel responsibility results as markdown or latex.

    Groups results by evaluation point when multiple evaluations are present.
    fmt: "markdown" (default) or "latex"
    """
    from alo_translator.query_generation import _sanitize_id
    aliases = model.aliases
    latex = fmt == "latex"

    CHECK_MD = "✓"
    EMPTY_MD = " "
    CHECK_TEX = r"\ding{51}"
    EMPTY_TEX = "~"

    eval_points = model.require_evaluations()

    sections = []
    for emom, ehist, etgt in eval_points:
        prop_id = _sanitize_id(etgt)
        scope = _sanitize_id(f"{emom}_{ehist}_{etgt}")
        suffix = f"_{prop_id}_{scope}"

        COLS = ("pres", "sres", "res", "dxstit", "but", "ness")
        agent_results = defaultdict(lambda: {c: False for c in COLS})

        for query in model.queries:
            qid = query.query_id
            if not qid or not qid.endswith(suffix):
                continue
            middle = qid[:-len(suffix)]
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

        def _agent_display(agent_str: str) -> str:
            parts = agent_str.split("_")
            names = [aliases.get(p, f"Agent {p}") for p in parts]
            if len(names) == 1:
                return names[0]
            return "{" + ", ".join(names) + "}"

        def _sort_key(a):
            parts = a.split("_")
            return (len(parts), parts)

        sorted_agents = sorted(agent_results.keys(), key=_sort_key)

        if latex:
            # Build header line
            outcome_qid = f"outcome_{scope}"
            holds = outcome_qid in satisfied_ids
            _, index = _outcome_index(model, ehist, etgt, emom)
            tgt_desc = aliases.get(etgt, etgt)
            holds_str = "holds" if holds else "does not hold"
            outcome_label = f"\\texttt{{{etgt}}}" + (f" ({tgt_desc})" if tgt_desc != etgt else "")
            cga_dict = model.histories[ehist].actions_at.get(emom, {}) if ehist in model.histories else {}
            cga = _cga_str(cga_dict, aliases) if cga_dict else "{}"
            cga_tex = cga.replace("{", r"\{").replace("}", r"\}")
            header = (
                "\\textbf{At \\texttt{" + f"{emom}/{ehist}" + "}, "
                "CGA: \\texttt{" + cga_tex + "}, outcome: " + outcome_label + ", " + holds_str + "}"
            )
            col_spec = "|l|" + "l|" * len(COLS)
            col_labels = {"ness": "NESS"}
            col_header = " & ".join(
                [r"\textbf{Agent}"] + [r"\textbf{" + col_labels.get(c, c) + "}" for c in COLS]
            )
            rows = []
            for agent in sorted_agents:
                r = agent_results[agent]
                display = _agent_display(agent)
                if display.startswith("{"):
                    display = r"\{" + display[1:-1] + r"\}"
                cells = " & ".join(CHECK_TEX if r[c] else EMPTY_TEX for c in COLS)
                rows.append(f"\\textbf{{{display}}} & {cells} \\\\")
            block = "\n".join([
                header,
                "",
                "\\smallskip",
                f"\\begin{{tabular}}{{{col_spec}}}",
                "\\hline",
                col_header + r" \\ \hline",
                *rows,
                "\\hline",
                "\\end{tabular}",
            ])
            sections.append(block)
        else:
            lines = [
                _section_header_layered(model, emom, ehist, etgt, satisfied_ids),
                "",
                "| Agent | pres | sres | res | dxstit | but | ness |",
                "|-------|------|------|-----|--------|-----|------|",
            ]
            for agent in sorted_agents:
                r = agent_results[agent]
                display = _agent_display(agent)
                row = [display] + [CHECK_MD if r[k] else EMPTY_MD for k in COLS]
                lines.append("| " + " | ".join(row) + " |")
            sections.append("\n".join(lines))

    sep = "\n\n\\medskip\n" if latex else "\n\n"
    return sep.join(sections)


def run_analysis_konclude(model, result_prop: str, eval_history: str,
                          ness_empty_sufficient: bool = True) -> Optional[Set[str]]:
    """Run responsibility analysis using Konclude OWL reasoner. Returns satisfied query IDs."""
    err = _validate_formula(result_prop)
    if err:
        st.error(f"Invalid outcome proposition `{result_prop}`: {err}")
        return None
    try:
        model = setup_queries(model, result_prop, eval_history)

        strategy = EquivFullCardinalityStrategy()
        serializer = OWLSerializer(model,
                                   evaluation_moment=model.evaluation_moment,
                                   evaluation_history=eval_history,
                                   strategy=strategy)
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


def _section_header_flat(model, eval_point: str, result_prop: str) -> str:
    """Build the At/CGA header for a single-evaluation-point results table."""
    emom, _, ehist = eval_point.partition("/")
    if not ehist:
        ehist = eval_point
        emom = "m"

    aliases = model.aliases

    hp = model.histories.get(ehist)
    cga_dict = hp.actions_at.get(emom, {}) if hp else {}
    cga = _cga_str(cga_dict, aliases) if cga_dict else "{}"

    prop_desc = aliases.get(result_prop, result_prop)
    outcome_label = f"`{result_prop}`" + (f" ({prop_desc})" if prop_desc != result_prop else "")
    return (
        f"**At:** `{emom}/{ehist}`  \n"
        f"**CGA:** `{cga}`  \n"
        f"**Outcome:** {outcome_label}"
    )


def format_results_table(model, satisfied_query_ids: Set[str], result_prop: str,
                         show_legend: bool = True, eval_point: str = "") -> str:
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

    if eval_point:
        header = _section_header_flat(model, eval_point, result_prop)
    else:
        result_desc = aliases.get(result_prop, result_prop)
        header = f"**Outcome**: `{result_prop}` ({result_desc})"

    lines = [
        header,
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
