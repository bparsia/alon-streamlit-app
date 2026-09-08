"""
Regression tests for the SPARQL/MINUS responsibility-analysis path
(run_analysis_konclude_sparql_layered) against the same canonical
baselines test_konclude_baselines.py checks the OWL/realization path
against.

Mirrors that file's shape/skip-if-absent convention. Baselines in
tests/fixtures/konclude_baselines.json are backend-agnostic (satisfied
query IDs for a given model+eval point) -- both the realization path and
this SPARQL path are checked against the identical expected answer.

Skipped automatically if Konclude binary is not found, same as
test_konclude_baselines.py.
"""

import json
from pathlib import Path

import pytest

BASELINES_PATH = Path(__file__).parent / "fixtures" / "konclude_baselines.json"
MODELS_DIR = Path(__file__).parent.parent / "streamlit_app" / "models"


def load_baselines():
    with open(BASELINES_PATH) as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def find_konclude() -> Path | None:
    """Find Konclude binary via reasoner_config.toml, else None."""
    from alo_translator.reasoners.config import load_config
    root = Path(__file__).parent.parent
    for config_path in [root / "reasoner_config.toml", Path("reasoner_config.toml")]:
        try:
            config = load_config(config_path)
            p = Path(config.reasoners["konclude"].path)
            if not p.is_absolute():
                p = config_path.parent / p
            if p.exists():
                return p
        except Exception:
            continue
    return None


def konclude_available():
    return find_konclude() is not None


def run_theory_sparql(mmd_path: Path):
    """Run run_analysis_konclude_sparql_layered on a .mmd model file,
    return the satisfied-formula strings (unscoped, comparable to the
    OWL-path baselines) for the m/h1/q evaluation point.

    Query IDs from run_analysis_konclude_sparql_layered are scoped
    (setup_layered_queries appends "_{moment}_{history}_{target}"), and
    include a synthetic "outcome_*" entry the OWL baselines don't have --
    both stripped/filtered here to make the comparison apples-to-apples
    with konclude_baselines.json's plain query_id-based satisfied_queries
    list (NOT satisfied_formulas, which test_konclude_baselines.py uses --
    the SPARQL path doesn't currently expose formula strings the way
    run_theory's realization-based path does, only query IDs).
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from alo_translator.parsers.dbt_parser import parse_dbt_diagram
    import streamlit_app.utils as u

    model = parse_dbt_diagram(mmd_path.read_text())
    model.evaluations = [("m", "h1", "q")]

    errors = []
    u.st.error = lambda msg: errors.append(msg)

    result = u.run_analysis_konclude_sparql_layered(model)
    if result is None:
        pytest.fail(f"run_analysis_konclude_sparql_layered failed: {errors}")

    scope_suffix = "_m_h1_q"
    return {
        qid[: -len(scope_suffix)]
        for qid in result
        if qid.endswith(scope_suffix) and not qid.startswith("outcome")
    }


@pytest.fixture(scope="module")
def baselines():
    return load_baselines()


@pytest.mark.skipif(not konclude_available(), reason="Konclude binary not found")
class TestKoncludeSparqlBaselines:

    def test_theory_3_1(self, baselines):
        b = baselines["3.1"]
        satisfied = run_theory_sparql(MODELS_DIR / "3.1.mmd")
        expected = set(b["satisfied_queries"])
        assert satisfied == expected, (
            f"Theory 3.1 (SPARQL path) mismatch\n"
            f"  Got ({len(satisfied)}):      {sorted(satisfied)}\n"
            f"  Expected ({len(expected)}): {sorted(expected)}"
        )

    def test_theory_3_5(self, baselines):
        b = baselines["3.5"]
        satisfied = run_theory_sparql(MODELS_DIR / "3.5.mmd")
        expected = set(b["satisfied_queries"])
        assert satisfied == expected, (
            f"Theory 3.5 (SPARQL path) mismatch\n"
            f"  Got ({len(satisfied)}):      {sorted(satisfied)}\n"
            f"  Expected ({len(expected)}): {sorted(expected)}"
        )
