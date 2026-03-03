"""
TOML parser for ALOn model specifications (Pass 1).

This module provides simple TOML loading functionality using Python's
built-in tomllib library (Python 3.11+).

The actual model building (semantic analysis) is handled by builder.py (Pass 2).
"""

import tomllib
from pathlib import Path
from typing import Dict, Any


def load_toml(file_path: str) -> Dict[str, Any]:
    """
    Load a TOML file and return the parsed dictionary (Pass 1).

    This is a thin wrapper around tomllib.load() that handles file I/O.
    Use builder.py for converting the dict into an ALOModel (Pass 2).

    Args:
        file_path: Path to the TOML file

    Returns:
        Dictionary containing the parsed TOML data

    Raises:
        FileNotFoundError: If the file doesn't exist
        tomllib.TOMLDecodeError: If the TOML is malformed
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"TOML file not found: {file_path}")

    with open(path, "rb") as f:
        return tomllib.load(f)


def load_toml_string(toml_string: str) -> Dict[str, Any]:
    """
    Parse a TOML string and return the dictionary (Pass 1).

    Args:
        toml_string: TOML content as a string

    Returns:
        Dictionary containing the parsed TOML data

    Raises:
        tomllib.TOMLDecodeError: If the TOML is malformed
    """
    return tomllib.loads(toml_string)


# Backwards compatibility: keep parse_toml_file() as a wrapper
def parse_toml_file(file_path: str):
    """
    Legacy function for backwards compatibility.

    **DEPRECATED**: Use builder.build_model(load_toml(file_path)) instead.

    This will import builder.py and build a complete model.
    """
    from .builder import build_model
    toml_dict = load_toml(file_path)
    return build_model(toml_dict)


def parse_toml_string(toml_string: str):
    """
    Legacy function for backwards compatibility.

    **DEPRECATED**: Use builder.build_model(load_toml_string(toml_string)) instead.
    """
    from .builder import build_model
    toml_dict = load_toml_string(toml_string)
    return build_model(toml_dict)
