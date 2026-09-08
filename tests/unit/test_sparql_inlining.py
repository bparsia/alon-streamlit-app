"""
Unit tests for streamlit_app.utils's fN-reference inlining helpers
(_fN_expansion_map, _inline_fN_references), used by
run_analysis_konclude_sparql_layered to make each SPARQL query fully
self-contained (no shared OWL-class state between queries -- see
docs/sparql_serializer.md and that function's docstring).
"""

import pytest

import streamlit_app.utils as u


def test_fN_expansion_map_parses_axiom_strings():
    axioms = [
        "[](free_do(sd1) -> Xq) => f2",
        "(do(sd1) & f2 & ~[]Xq & Xq) => f1",
    ]
    result = u._fN_expansion_map(axioms)
    assert result == {
        "f2": "[](free_do(sd1) -> Xq)",
        "f1": "(do(sd1) & f2 & ~[]Xq & Xq)",
    }


def test_fN_expansion_map_ignores_non_axiom_strings():
    # Defensive: any string without "=>" is skipped rather than raising
    # (ExpanderTransformer.axioms is documented as always containing
    # "expansion => name" strings, but this guards against a malformed
    # or unexpected entry silently corrupting the map instead of erroring
    # loudly elsewhere).
    result = u._fN_expansion_map(["not an axiom", "do(sd1) => f1"])
    assert result == {"f1": "do(sd1)"}


def test_inline_single_reference():
    expansions = {"f1": "do(sd1) & Xq"}
    result = u._inline_fN_references("f1", expansions)
    assert result == "(do(sd1) & Xq)"


def test_inline_recursive_references():
    """f1 references f2, which must itself be inlined before the fixed
    point is reached -- not just one substitution pass."""
    expansions = {
        "f1": "do(sd1) & f2",
        "f2": "[]Xq",
    }
    result = u._inline_fN_references("f1", expansions)
    assert "f2" not in result
    assert "[]Xq" in result


def test_inline_leaves_non_fN_tokens_alone():
    """Regression test: the very first version of this helper was called
    with a bare formula that was itself already-primitive (the "outcome"
    query, formula_string "Xq", which never goes through
    ExpanderTransformer._name_for at all since `next` doesn't cache/name
    its result) -- inlining must be a no-op for tokens that aren't real
    fN names, not raise a KeyError."""
    expansions = {"f1": "do(sd1)"}
    result = u._inline_fN_references("Xq", expansions)
    assert result == "Xq"


def test_inline_does_not_match_fN_as_substring():
    """Whole-token matching only: a hypothetical proposition or action
    name containing "f1" as a substring (not equal to it) must not be
    corrupted by the substitution."""
    expansions = {"f1": "do(sd1)"}
    # "off1" contains "f1" as a substring but is not the token "f1"
    result = u._inline_fN_references("do(off1)", expansions)
    assert result == "do(off1)"


def test_inline_word_boundary_before_and_after():
    expansions = {"f1": "q"}
    result = u._inline_fN_references("f1 & f10", {"f1": "q", "f10": "p"})
    # f1 and f10 are distinct tokens (word-boundary regex) -- f1 must not
    # accidentally match the "f1" prefix of "f10".
    assert "(q)" in result
    assert "(p)" in result
