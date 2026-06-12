"""
Regression + performance tests for the pyDatalog evaluation pipeline.

Correctness is checked against the canonical Konclude baselines in
tests/fixtures/konclude_baselines.json.

Performance thresholds are generous but catch pathological regressions
(e.g. accidentally calling expand_queries() which costs ~70s for theory 3.5).

Run with:
  pytest tests/test_datalog_baselines.py -v
"""

import json
import time
import pytest
from pathlib import Path

BASELINES_PATH = Path(__file__).parent / "fixtures" / "konclude_baselines.json"
MODELS_DIR = Path(__file__).parent.parent / "streamlit_app" / "models"

# Wall-clock limits (seconds) — generous, just catch catastrophic regressions
PERF_LIMITS = {
    "3.1": 5.0,
    "3.5": 15.0,   # Was 71s with accidental expand_queries() call
    "3.6": 5.0,
    "3.7": 5.0,
}


def load_baselines():
    with open(BASELINES_PATH) as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def run_datalog(mmd_path: Path):
    """Run pyDatalog evaluation pipeline from a .mmd model file."""
    from alo_translator.parsers.dbt_parser import parse_dbt_diagram
    from alo_translator.parsers.builder import parse_formula
    from alo_translator.query_generation import ResponsibilityConfig, generate_queries
    from alo_translator.serializers.layered_datalog_index import LayeredDatalogIndexSerializer

    model = parse_dbt_diagram(mmd_path.read_text())

    model.responsibility_config = ResponsibilityConfig(
        target_proposition="q",
        agents="all",
        groups="all",
        responsibility_types=["pres", "sres", "res", "dxstit", "but", "ness"],
        history="h1",
    )
    model.queries = generate_queries(model)
    for q in model.queries:
        if q.formula_ast is None:
            q.formula_ast = parse_formula(q.formula_string)

    serializer = LayeredDatalogIndexSerializer(model, evaluation_history="h1")
    results = serializer.evaluate()
    return sorted(qid for qid, r in results.items() if r.get("result"))


@pytest.fixture(scope="module")
def baselines():
    return load_baselines()


class TestDatalogCorrectness:

    def test_theory_3_1(self, baselines):
        b = baselines["3.1"]
        satisfied = run_datalog(MODELS_DIR / "3.1.mmd")
        assert satisfied == b["satisfied_queries"], (
            f"Theory 3.1 mismatch\n"
            f"  Got ({len(satisfied)}):      {satisfied}\n"
            f"  Expected ({b['satisfied_count']}): {b['satisfied_queries']}"
        )

    def test_theory_3_5(self, baselines):
        b = baselines["3.5"]
        satisfied = run_datalog(MODELS_DIR / "3.5.mmd")
        assert satisfied == b["satisfied_queries"], (
            f"Theory 3.5 mismatch\n"
            f"  Got ({len(satisfied)}):      {satisfied}\n"
            f"  Expected ({b['satisfied_count']}): {b['satisfied_queries']}"
        )

    def test_theory_3_6(self, baselines):
        b = baselines["3.6"]
        satisfied = run_datalog(MODELS_DIR / "3.6.mmd")
        assert satisfied == b["satisfied_queries"], (
            f"Theory 3.6 mismatch\n"
            f"  Got ({len(satisfied)}):      {satisfied}\n"
            f"  Expected ({b['satisfied_count']}): {b['satisfied_queries']}"
        )

    def test_theory_3_7(self, baselines):
        b = baselines["3.7"]
        satisfied = run_datalog(MODELS_DIR / "3.7.mmd")
        assert satisfied == b["satisfied_queries"], (
            f"Theory 3.7 mismatch\n"
            f"  Got ({len(satisfied)}):      {satisfied}\n"
            f"  Expected ({b['satisfied_count']}): {b['satisfied_queries']}"
        )


class TestDatalogPerformance:

    @pytest.mark.parametrize("theory_id,limit", [
        ("3.1", PERF_LIMITS["3.1"]),
        ("3.5", PERF_LIMITS["3.5"]),
        ("3.6", PERF_LIMITS["3.6"]),
        ("3.7", PERF_LIMITS["3.7"]),
    ])
    def test_performance(self, theory_id, limit):
        t0 = time.perf_counter()
        run_datalog(MODELS_DIR / f"{theory_id}.mmd")
        elapsed = time.perf_counter() - t0
        assert elapsed < limit, (
            f"Theory {theory_id} took {elapsed:.1f}s, limit is {limit}s. "
            f"Check for accidental expand_queries() call or regression in expansion."
        )
