"""
Regression tests using the versioned result registry.

Each test runs the current pipeline and compares against the most recent
verified registry entry for that model/variant. Tests are skipped if no
verified entry exists.

Run with:
  pytest tests/test_registry.py -v
"""

import pytest
from pathlib import Path
from tests.registry import check_regression, _run_datalog

MODELS_DIR = Path(__file__).parent.parent / "streamlit_app" / "models"


def _get_current_datalog(model_id: str) -> dict:
    """Run datalog pipeline and return {formula: bool} dict."""
    mmd_path = MODELS_DIR / f"{model_id}.mmd"
    return _run_datalog(mmd_path.read_text())


@pytest.mark.parametrize("theory_id", ["3.1", "3.5", "3.6", "3.7"])
def test_datalog_no_regression(theory_id):
    """Current datalog results must match the most recent verified registry entry."""
    current = _get_current_datalog(theory_id)
    disagreements = check_regression(theory_id, "datalog", current)
    assert not disagreements, (
        f"Theory {theory_id} datalog regressed against verified baseline:\n"
        + "\n".join(f"  {d}" for d in disagreements)
    )
