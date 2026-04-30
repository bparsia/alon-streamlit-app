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


def run_datalog(toml_path: str):
    """
    Run pyDatalog evaluation pipeline.

    NOTE: do NOT call expand_queries() here — DatalogIndexSerializer
    handles expansion internally via PyDatalogExpanderTransformer.
    Calling expand_queries() first triggers the hierarchical OWL expander
    which takes ~70s for theory 3.5 and produces no useful output for Datalog.
    """
    from alo_translator.parsers.toml_parser import parse_toml_file
    from alo_translator.parsers.builder import parse_queries
    from alo_translator.serializers.datalog_index import DatalogIndexSerializer

    model = parse_toml_file(toml_path)
    model = parse_queries(model)
    serializer = DatalogIndexSerializer(model, evaluation_history="h1")
    results = serializer.evaluate()
    return sorted(qid for qid, r in results.items() if r.get("result"))


@pytest.fixture(scope="module")
def baselines():
    return load_baselines()


class TestDatalogCorrectness:

    def test_theory_3_1(self, baselines):
        b = baselines["3.1"]
        satisfied = run_datalog(b["toml"])
        assert satisfied == b["satisfied_queries"], (
            f"Theory 3.1 mismatch\n"
            f"  Got ({len(satisfied)}):      {satisfied}\n"
            f"  Expected ({b['satisfied_count']}): {b['satisfied_queries']}"
        )

    def test_theory_3_5(self, baselines):
        b = baselines["3.5"]
        satisfied = run_datalog(b["toml"])
        assert satisfied == b["satisfied_queries"], (
            f"Theory 3.5 mismatch\n"
            f"  Got ({len(satisfied)}):      {satisfied}\n"
            f"  Expected ({b['satisfied_count']}): {b['satisfied_queries']}"
        )

    def test_theory_3_6(self, baselines):
        b = baselines["3.6"]
        satisfied = run_datalog(b["toml"])
        assert satisfied == b["satisfied_queries"], (
            f"Theory 3.6 mismatch\n"
            f"  Got ({len(satisfied)}):      {satisfied}\n"
            f"  Expected ({b['satisfied_count']}): {b['satisfied_queries']}"
        )

    def test_theory_3_7(self, baselines):
        b = baselines["3.7"]
        satisfied = run_datalog(b["toml"])
        assert satisfied == b["satisfied_queries"], (
            f"Theory 3.7 mismatch\n"
            f"  Got ({len(satisfied)}):      {satisfied}\n"
            f"  Expected ({b['satisfied_count']}): {b['satisfied_queries']}"
        )


class TestDatalogPerformance:

    @pytest.mark.parametrize("theory_id,toml,limit", [
        ("3.1", "theories/3.1_auto.toml", PERF_LIMITS["3.1"]),
        ("3.5", "theories/3.5_auto.toml", PERF_LIMITS["3.5"]),
        ("3.6", "theories/3.6_auto.toml", PERF_LIMITS["3.6"]),
        ("3.7", "theories/3.7_auto.toml", PERF_LIMITS["3.7"]),
    ])
    def test_performance(self, theory_id, toml, limit):
        t0 = time.perf_counter()
        run_datalog(toml)
        elapsed = time.perf_counter() - t0
        assert elapsed < limit, (
            f"Theory {theory_id} took {elapsed:.1f}s, limit is {limit}s. "
            f"Check for accidental expand_queries() call or regression in expansion."
        )
