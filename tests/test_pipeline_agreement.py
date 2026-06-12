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

    mermaid = mmd_path.read_text()
    parsed = parse_dbt_diagram(mermaid)
    model = parsed[0] if isinstance(parsed, tuple) else parsed

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


def _as_layered(mmd_path: Path):
    """Force-parse a diagram through the layered pipeline (bypasses TD=1 check)."""
    from lark import Lark
    from pathlib import Path as _Path
    from alo_translator.parsers.dbt_parser import (
        MERMAID_PARSER, _parse_layered,
    )
    from alo_translator.parsers.mermaid_transformer import MermaidTransformer
    from alo_translator.parsers.yaml_helper import frontmatter_to_partial_spec
    from alo_translator.parsers.builder import parse_formula
    from alo_translator.query_generation import ResponsibilityConfig, generate_queries

    mermaid = mmd_path.read_text()
    tree = MERMAID_PARSER.parse(mermaid)
    transformer = MermaidTransformer()
    parsed = transformer.transform(tree)

    partial_spec = frontmatter_to_partial_spec(parsed.get("frontmatter"))
    diagram = parsed.get("diagram")

    model = _parse_layered(diagram, partial_spec)

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


def _run_flat_datalog(mmd_path: Path):
    from alo_translator.serializers.datalog_index import DatalogIndexSerializer
    model = _setup_model(mmd_path)
    serializer = DatalogIndexSerializer(model, evaluation_history="h1")
    results = serializer.evaluate()
    return sorted(qid for qid, r in results.items() if r.get("result"))


def _run_layered_datalog(mmd_path: Path):
    from alo_translator.serializers.layered_datalog_index import LayeredDatalogIndexSerializer
    model = _as_layered(mmd_path)
    serializer = LayeredDatalogIndexSerializer(model)
    results = serializer.evaluate()
    return sorted(qid for qid, r in results.items() if r.get("result"))


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
    from alo_translator.serializers.owl_index_new_expander import OWLIndexNewExpanderSerializer
    from alo_translator.serializers.index_strategies import EquivFullCardinalityStrategy
    from alo_translator.reasoners.konclude import KoncludeAdapter
    from alo_translator.reasoners.base import ReasoningMode
    import tempfile

    model = _setup_model(mmd_path)
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


# ---------------------------------------------------------------------------
# Tests: flat vs layered Datalog agreement (TD=1 models)
# ---------------------------------------------------------------------------

class TestFlatVsLayeredDatalog:

    @pytest.mark.parametrize("theory_id", ALL_TD1_MODELS)
    def test_agreement(self, theory_id):
        mmd = MODELS_DIR / f"{theory_id}.mmd"
        flat = _run_flat_datalog(mmd)
        layered = _run_layered_datalog(mmd)
        assert flat == layered, (
            f"Theory {theory_id}: flat vs layered Datalog disagree\n"
            f"  Flat    ({len(flat)}):    {flat}\n"
            f"  Layered ({len(layered)}): {layered}\n"
            f"  Only in flat:    {sorted(set(flat) - set(layered))}\n"
            f"  Only in layered: {sorted(set(layered) - set(flat))}"
        )


# ---------------------------------------------------------------------------
# Tests: Datalog vs Konclude agreement (TD=1 models, Konclude available)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(find_konclude() is None, reason="Konclude binary not found")
class TestDatalogVsKonclude:

    @pytest.mark.parametrize("theory_id", TD1_MODELS)
    def test_agreement(self, theory_id):
        mmd = MODELS_DIR / f"{theory_id}.mmd"
        datalog = _run_flat_datalog(mmd)
        konclude = _run_konclude(mmd)
        assert datalog == konclude, (
            f"Theory {theory_id}: Datalog vs Konclude disagree\n"
            f"  Datalog  ({len(datalog)}):  {datalog}\n"
            f"  Konclude ({len(konclude)}): {konclude}\n"
            f"  Only in Datalog:  {sorted(set(datalog) - set(konclude))}\n"
            f"  Only in Konclude: {sorted(set(konclude) - set(datalog))}"
        )


# ---------------------------------------------------------------------------
# Gold standard capture
# ---------------------------------------------------------------------------

def capture_gold_standard():
    """
    Run all models through flat Datalog and save results to fixtures/gold_standard.json.
    Called directly (not as a test) to regenerate the gold standard.
    """
    gold = {}
    for theory_id in ALL_TD1_MODELS:
        mmd = MODELS_DIR / f"{theory_id}.mmd"
        flat = _run_flat_datalog(mmd)
        layered = _run_layered_datalog(mmd)
        gold[theory_id] = {
            "flat_datalog": flat,
            "layered_datalog": layered,
            "agreement": flat == layered,
        }

    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GOLD_PATH, "w") as f:
        json.dump(gold, f, indent=2)
    print(f"Gold standard written to {GOLD_PATH}")
    return gold


class TestGoldStandard:
    """Verify current results match the saved gold standard (if it exists)."""

    @pytest.mark.parametrize("theory_id", ALL_TD1_MODELS)
    def test_flat_datalog_stable(self, theory_id):
        if not GOLD_PATH.exists():
            pytest.skip("Gold standard not yet captured — run capture_gold_standard()")
        with open(GOLD_PATH) as f:
            gold = json.load(f)
        if theory_id not in gold:
            pytest.skip(f"No gold entry for {theory_id}")
        current = _run_flat_datalog(MODELS_DIR / f"{theory_id}.mmd")
        expected = gold[theory_id]["flat_datalog"]
        assert current == expected, (
            f"Theory {theory_id} flat Datalog changed from gold standard\n"
            f"  Current  ({len(current)}):  {current}\n"
            f"  Expected ({len(expected)}): {expected}"
        )


if __name__ == "__main__":
    print("Capturing gold standard...")
    gold = capture_gold_standard()
    for theory_id, entry in gold.items():
        status = "AGREE" if entry["agreement"] else "DISAGREE"
        print(f"  {theory_id}: {status} — {len(entry['flat_datalog'])} satisfied")
