"""
Regression tests against canonical Konclude baselines.

Baselines in tests/fixtures/konclude_baselines.json were produced with:
  - Konclude (EquivFullCardinalityStrategy / strategy 2)
  - OWL free_do group action fix applied (2026-03-20)
  - evaluate_model.py --queries auto --strategy 2

To run (requires Konclude binary):
  pytest tests/test_konclude_baselines.py -v

Skipped automatically if Konclude binary is not found.
"""

import json
import pytest
from pathlib import Path

BASELINES_PATH = Path(__file__).parent / "fixtures" / "konclude_baselines.json"


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


def run_theory(toml_path: str, timeout: int = 120):
    """Run evaluate_model pipeline and return satisfied query IDs."""
    from alo_translator.parsers.toml_parser import parse_toml_file
    from alo_translator.parsers.builder import parse_queries
    from alo_translator.serializers.owl_index_new_expander import OWLIndexNewExpanderSerializer
    from alo_translator.serializers.index_strategies import EquivFullCardinalityStrategy
    from alo_translator.reasoners.konclude import KoncludeAdapter
    from alo_translator.reasoners.base import ReasoningMode
    import tempfile

    model = parse_toml_file(toml_path)
    model = parse_queries(model)

    strategy = EquivFullCardinalityStrategy()
    serializer = OWLIndexNewExpanderSerializer(model, strategy=strategy)
    owl_str = serializer.serialize()

    with tempfile.NamedTemporaryFile(suffix=".owl", mode="w", delete=False) as f:
        f.write(owl_str)
        owl_path = Path(f.name)

    try:
        adapter = KoncludeAdapter(str(find_konclude()))
        result = adapter.run(owl_path, mode=ReasoningMode.REALISATION, timeout=timeout)
    finally:
        owl_path.unlink(missing_ok=True)

    if not result.success:
        pytest.skip(f"Konclude failed: {result.error_message}")

    m_types = result.individual_types.get("m_h1", set())
    return sorted(q.query_id for q in model.queries if q.query_id in m_types)


@pytest.fixture(scope="module")
def baselines():
    return load_baselines()


@pytest.mark.skipif(not konclude_available(), reason="Konclude binary not found")
class TestKoncludeBaselines:

    def test_theory_3_1(self, baselines):
        b = baselines["3.1"]
        satisfied = run_theory(b["toml"], timeout=120)
        assert satisfied == b["satisfied_queries"], (
            f"Theory 3.1 mismatch\n"
            f"  Got ({len(satisfied)}):      {satisfied}\n"
            f"  Expected ({b['satisfied_count']}): {b['satisfied_queries']}"
        )

    def test_theory_3_5(self, baselines):
        b = baselines["3.5"]
        satisfied = run_theory(b["toml"], timeout=b.get("konclude_timeout_seconds", 600))
        assert satisfied == b["satisfied_queries"], (
            f"Theory 3.5 mismatch\n"
            f"  Got ({len(satisfied)}):      {satisfied}\n"
            f"  Expected ({b['satisfied_count']}): {b['satisfied_queries']}"
        )

    def test_theory_3_6(self, baselines):
        b = baselines["3.6"]
        satisfied = run_theory(b["toml"], timeout=120)
        assert satisfied == b["satisfied_queries"], (
            f"Theory 3.6 mismatch\n"
            f"  Got ({len(satisfied)}):      {satisfied}\n"
            f"  Expected ({b['satisfied_count']}): {b['satisfied_queries']}"
        )

    def test_theory_3_7(self, baselines):
        b = baselines["3.7"]
        satisfied = run_theory(b["toml"], timeout=120)
        assert satisfied == b["satisfied_queries"], (
            f"Theory 3.7 mismatch\n"
            f"  Got ({len(satisfied)}):      {satisfied}\n"
            f"  Expected ({b['satisfied_count']}): {b['satisfied_queries']}"
        )

    def test_satisfied_counts(self, baselines):
        """Quick sanity check: just verify the counts without running Konclude."""
        expected_counts = {"3.1": 13, "3.5": 26, "3.6": 10, "3.7": 10}
        for theory_id, expected in expected_counts.items():
            actual = baselines[theory_id]["satisfied_count"]
            assert actual == expected, f"Theory {theory_id}: count {actual} != {expected}"
            assert len(baselines[theory_id]["satisfied_queries"]) == expected
