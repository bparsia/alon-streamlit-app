"""Pytest configuration and shared fixtures."""

import pytest
from pathlib import Path


@pytest.fixture
def fixtures_dir():
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def theories_dir(fixtures_dir):
    """Return path to theory fixtures."""
    return fixtures_dir / "theories"


@pytest.fixture
def golden_owl_dir(fixtures_dir):
    """Return path to golden OWL outputs."""
    return fixtures_dir / "golden_owl"
