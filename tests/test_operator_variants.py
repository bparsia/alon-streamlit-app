"""
Cross-variant agreement tests for the res/ness operator formulations
introduced in docs/msc_operator_design.md.

Three variants of res are meant to be logically equivalent: the
original res(), the MSC-based res_msc()/ness_via_msc() reformulation,
and res_candidate()+ness() composed outside the reasoner. This file
asserts they actually agree, across every agent/coalition in a small
set of real models, rather than trusting the ad hoc checks that
motivated the design.

Uses tests/registry.py's run_operator_variant_comparison, which is
itself reusable if/when more variants are added later (e.g. a batched
MSC-retrieval query) -- see that module's OPERATOR_VARIANT_GROUPS.

Skipped automatically if Konclude binary is not found (same pattern as
test_konclude_baselines.py).
"""

from pathlib import Path

import pytest

from tests.registry import run_operator_variant_comparison

MODELS_DIR = Path(__file__).parent.parent / "streamlit_app" / "models"


def _find_konclude():
    from alo_translator.reasoners.config import load_config

    root = Path(__file__).parent.parent
    for config_path in [root / "reasoner_config.toml"]:
        if config_path.exists():
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


def _konclude_available():
    return _find_konclude() is not None


pytestmark = pytest.mark.skipif(not _konclude_available(), reason="Konclude binary not found")


@pytest.mark.parametrize("model_id", ["3.1", "3.5", "3.6", "3.7"])
def test_res_variants_agree(model_id):
    """res(), res_msc(), and res_candidate()+ness() (composed outside
    the reasoner) must produce identical results for every
    agent/coalition."""
    mmd_path = MODELS_DIR / f"{model_id}.mmd"
    if not mmd_path.exists():
        pytest.skip(f"Model {model_id} not found")

    result = run_operator_variant_comparison(mmd_path.read_text())
    if not result:
        pytest.skip("Konclude run failed or unavailable")

    res_group = result["res"]
    assert res_group["results"], f"{model_id}: no res results captured"
    assert res_group["disagreements"] == [], (
        f"{model_id}: res/res_msc/res_candidate_and_ness disagree:\n"
        + "\n".join(res_group["disagreements"])
    )


@pytest.mark.parametrize("model_id", ["3.1", "3.5", "3.6", "3.7"])
def test_ness_variants_agree(model_id):
    """ness() and ness_via_msc() (the MSC-based reformulation) must
    produce identical results for every agent/coalition's actual
    action."""
    mmd_path = MODELS_DIR / f"{model_id}.mmd"
    if not mmd_path.exists():
        pytest.skip(f"Model {model_id} not found")

    result = run_operator_variant_comparison(mmd_path.read_text())
    if not result:
        pytest.skip("Konclude run failed or unavailable")

    ness_group = result["ness"]
    assert ness_group["results"], f"{model_id}: no ness results captured"
    assert ness_group["disagreements"] == [], (
        f"{model_id}: ness/ness_via_msc disagree:\n"
        + "\n".join(ness_group["disagreements"])
    )


def test_res_candidate_composition_is_not_trivial():
    """Regression guard for the AND-composition bug this test file was
    written to catch: on 3.5, agent 3 has res_candidate=True but
    ness=False, so res_candidate_and_ness must come out False even
    though res_candidate alone is True -- confirms the composition
    actually uses ness's value rather than silently defaulting/passing
    through res_candidate's answer unchanged."""
    mmd_path = MODELS_DIR / "3.5.mmd"
    if not mmd_path.exists():
        pytest.skip("Model 3.5 not found")

    result = run_operator_variant_comparison(mmd_path.read_text())
    if not result:
        pytest.skip("Konclude run failed or unavailable")

    res_results = result["res"]["results"]
    assert "3" in res_results, "expected agent 3's row in 3.5's res comparison"
    row = res_results["3"]
    assert row["res"] is False, f"expected res=False for agent 3, got {row}"
    assert row["res_candidate_and_ness"] is False, (
        f"expected res_candidate_and_ness=False for agent 3 (real "
        f"divergence case: res_candidate is True but ness is False), got {row}"
    )
