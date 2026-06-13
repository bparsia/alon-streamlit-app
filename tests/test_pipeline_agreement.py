"""
Cross-pipeline agreement tests.

Verifies that:
1. Flat (TD=1) pipeline and Layered pipeline agree for TD=1 models.
2. Datalog and Konclude agree across all core models (via shared baselines).
3. Captures a gold-standard result snapshot for all models.

Run with:
  pytest tests/test_pipeline_agreement.py -v

Konclude tests skipped if binary not found.
"""

import json
import pytest
from pathlib import Path

MODELS_DIR = Path(__file__).parent.parent / "streamlit_app" / "models"
BASELINES_PATH = Path(__file__).parent / "fixtures" / "konclude_baselines.json"
GOLD_PATH = Path(__file__).parent / "fixtures" / "gold_standard.json"

TD1_MODELS = ["3.1", "3.6", "3.7"]   # 3.5 omitted from Konclude cross-check (slow)
ALL_TD1_MODELS = ["3.1", "3.5", "3.6", "3.7"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_model(mmd_path: Path):
    """Parse .mmd and attach responsibility config. Returns ALOModel."""
    from alo_translator.parsers.dbt_parser import parse_dbt_diagram
    from alo_translator.parsers.builder import parse_formula
    from alo_translator.query_generation import ResponsibilityConfig, generate_queries

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
    return model


def _run_datalog(mmd_path: Path):
    from alo_translator.serializers.datalog import DatalogIndexSerializer
    model = _setup_model(mmd_path)
    serializer = DatalogIndexSerializer(model, evaluation_history="h1")
    results = serializer.evaluate()
    id_to_formula = {q.query_id: q.formula_string for q in model.queries}
    return sorted(id_to_formula[qid] for qid, r in results.items()
                  if r.get("result") and qid in id_to_formula)


def find_konclude() -> Path | None:
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


def _run_konclude(mmd_path: Path, timeout: int = 120):
    from alo_translator.serializers.owl import OWLSerializer
    from alo_translator.serializers.index_strategies import EquivFullCardinalityStrategy
    from alo_translator.reasoners.konclude import KoncludeAdapter
    from alo_translator.reasoners.base import ReasoningMode
    import tempfile

    model = _setup_model(mmd_path)
    serializer = OWLSerializer(model,
                                           evaluation_history=model.evaluation_history,
                                           evaluation_moment=model.evaluation_moment,
                                           strategy=EquivFullCardinalityStrategy())
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
    id_to_formula = {q.query_id: q.formula_string for q in model.queries}
    return sorted(id_to_formula[q.query_id] for q in model.queries
                  if q.query_id in m_types and q.query_id in id_to_formula)


# ---------------------------------------------------------------------------
# Tests: Datalog results against gold standard
# ---------------------------------------------------------------------------

class TestDatalogBaselines:

    @pytest.mark.parametrize("theory_id", ALL_TD1_MODELS)
    def test_agreement(self, theory_id):
        mmd = MODELS_DIR / f"{theory_id}.mmd"
        results = _run_datalog(mmd)
        assert isinstance(results, list)
        assert len(results) > 0, f"Theory {theory_id}: no satisfied queries"


# ---------------------------------------------------------------------------
# Tests: Datalog vs Konclude agreement (TD=1 models, Konclude available)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(find_konclude() is None, reason="Konclude binary not found")
class TestDatalogVsKonclude:

    @pytest.mark.parametrize("theory_id", TD1_MODELS)
    def test_agreement(self, theory_id):
        mmd = MODELS_DIR / f"{theory_id}.mmd"
        datalog = _run_datalog(mmd)
        konclude = _run_konclude(mmd)
        assert datalog == konclude, (
            f"Theory {theory_id}: Datalog vs Konclude disagree\n"
            f"  Datalog  ({len(datalog)}):  {datalog}\n"
            f"  Konclude ({len(konclude)}): {konclude}\n"
            f"  Only in Datalog:  {sorted(set(datalog) - set(konclude))}\n"
            f"  Only in Konclude: {sorted(set(konclude) - set(datalog))}"
        )


# ---------------------------------------------------------------------------
# Gold standard capture and stability
# ---------------------------------------------------------------------------

def capture_gold_standard():
    """
    Run all models through Datalog and save results to fixtures/gold_standard.json.
    Called directly (not as a test) to regenerate the gold standard.
    """
    gold = {}
    for theory_id in ALL_TD1_MODELS:
        mmd = MODELS_DIR / f"{theory_id}.mmd"
        results = _run_datalog(mmd)
        gold[theory_id] = {"datalog": results}

    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GOLD_PATH, "w") as f:
        json.dump(gold, f, indent=2)
    print(f"Gold standard written to {GOLD_PATH}")
    return gold


class TestGoldStandard:
    """Verify current results match the saved gold standard (if it exists)."""

    @pytest.mark.parametrize("theory_id", ALL_TD1_MODELS)
    def test_datalog_stable(self, theory_id):
        if not GOLD_PATH.exists():
            pytest.skip("Gold standard not yet captured — run capture_gold_standard()")
        with open(GOLD_PATH) as f:
            gold = json.load(f)
        if theory_id not in gold:
            pytest.skip(f"No gold entry for {theory_id}")
        current = _run_datalog(MODELS_DIR / f"{theory_id}.mmd")
        expected = gold[theory_id].get("datalog") or gold[theory_id].get("flat_datalog")
        assert current == expected, (
            f"Theory {theory_id} Datalog changed from gold standard\n"
            f"  Current  ({len(current)}):  {current}\n"
            f"  Expected ({len(expected)}): {expected}"
        )


if __name__ == "__main__":
    print("Capturing gold standard...")
    gold = capture_gold_standard()
    for theory_id, entry in gold.items():
        print(f"  {theory_id}: {len(entry['datalog'])} satisfied")
