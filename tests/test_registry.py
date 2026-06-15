"""
Regression tests using the versioned result registry.

Each test runs the current pipeline and compares against the most recent
verified registry entry for that (model, variant) pair. Tests are skipped
if no verified entry exists for a variant.

Any translation/reasoner system captured and verified in the registry is
tested here — this is a change detector, not a correctness oracle.

Run with:
  pytest tests/test_registry.py -v
"""

import pytest
from pathlib import Path
from tests.registry import check_regression, load_registry, _run_datalog, _run_owl

MODELS_DIR = Path(__file__).parent.parent / "streamlit_app" / "models"

# Discover all (model, variant) pairs that have at least one verified entry.
_verified_pairs = sorted({
    (e["model"], variant)
    for e in load_registry()
    if e["verified"]
    for variant in e.get("variants_run", [])
})

_RUNNERS = {
    "datalog": lambda model_id: _run_datalog(
        (MODELS_DIR / f"{model_id}.mmd").read_text()
    ),
}


def _run_variant(model_id: str, variant: str) -> dict:
    if variant in _RUNNERS:
        return _RUNNERS[variant](model_id)
    if variant.startswith("owl_"):
        result = _run_owl((MODELS_DIR / f"{model_id}.mmd").read_text(), variant)
        if result is None:
            pytest.skip(f"Variant {variant} unavailable (reasoner not configured)")
        return result
    pytest.skip(f"No runner for variant {variant}")


@pytest.mark.parametrize("theory_id,variant", _verified_pairs)
def test_no_regression(theory_id, variant):
    """Current results must match the most recent verified registry entry."""
    current = _run_variant(theory_id, variant)
    disagreements = check_regression(theory_id, variant, current)
    assert not disagreements, (
        f"Theory {theory_id} / {variant} regressed against verified baseline:\n"
        + "\n".join(f"  {d}" for d in disagreements)
    )
