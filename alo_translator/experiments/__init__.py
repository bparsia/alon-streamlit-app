"""Experiment management for ALOn reasoner testing.

This package provides tools for running experiments across multiple
reasoners, translations, and test inputs with automated measurement collection.
"""

from .manifest import ExperimentManifest, ExperimentSpec, load_manifest
from .runner import ExperimentRunner, ExperimentResult

__all__ = [
    'ExperimentManifest',
    'ExperimentSpec',
    'load_manifest',
    'ExperimentRunner',
    'ExperimentResult',
]
