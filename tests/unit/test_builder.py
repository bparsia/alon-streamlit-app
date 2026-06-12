"""Unit tests for builder.py (Pass 2, 3)."""

import pytest
from alo_translator.model.core import ALOModel, GroupAction
from alo_translator.model.formula import (
    Prop, Next, Box, PDLBox, Implication, DoAction,
    PotentialResponsibility, IndividualAction, IndividualAgent
)
from alo_translator.parsers.builder import (
    build_model,
    parse_queries,
    expand_queries,
    parse_toml,
)
from alo_translator.parsers.toml_parser import load_toml_string


# ============================================================================
# Test Pass 2: build_model() - semantic analysis
# ============================================================================

def test_build_minimal_model():
    """Test building a minimal model with just actions."""
    toml_dict = {
        "Actions": {"1": ["a", "b"]},
    }
    model = build_model(toml_dict)

    assert "1" in model.get_all_agents()
    assert "a" in model.get_all_action_types()
    assert "b" in model.get_all_action_types()
    assert len(model.queries) == 0


def test_build_model_with_aliases():
    """Test parsing aliases section."""
    toml_dict = {
        "Actions": {"1": ["sd"]},
        "Aliases": {"1": "Alice", "sd": "shoots Dan"},
    }
    model = build_model(toml_dict)

    assert model.aliases["1"] == "Alice"
    assert model.aliases["sd"] == "shoots Dan"


def test_build_model_with_histories():
    """Test parsing histories section."""
    toml_dict = {
        "Actions": {"1": ["sd"], "2": ["ss"]},
        "Histories": {"h1": {"1": "sd", "2": "ss"}},
    }
    model = build_model(toml_dict)

    assert "h1" in model.named_histories
    h1 = model.named_histories["h1"]
    assert h1.actions == {"1": "sd", "2": "ss"}


def test_build_model_with_results():
    """Test parsing results section."""
    toml_dict = {
        "Actions": {"1": ["a"]},
        "Results": {"h1": ["q", "r"]},
    }
    model = build_model(toml_dict)

    assert len(model.results) == 1
    assert model.results[0].history_name == "h1"
    assert model.results[0].true_propositions == {"q", "r"}


def test_build_model_with_queries():
    """Test parsing queries section."""
    toml_dict = {
        "Actions": {"1": ["a"]},
        "Queries": {
            "Effects": ["Xq", "~[]Xq"],
            "Responsibility": ["[1 pres]q"],
        },
    }
    model = build_model(toml_dict)

    assert len(model.queries) == 3
    assert model.queries[0].formula_string == "Xq"
    assert model.queries[0].category == "Effects"
    assert model.queries[1].formula_string == "~[]Xq"
    assert model.queries[1].category == "Effects"
    assert model.queries[2].formula_string == "[1 pres]q"
    assert model.queries[2].category == "Responsibility"
    assert model.queries[0].formula_ast is None


def test_build_model_normalizes_agent_ids():
    """Test that agent IDs are normalized to strings."""
    toml_dict = {
        "Actions": {1: ["a"], 2: ["b"]},
    }
    model = build_model(toml_dict)

    assert "1" in model.get_all_agents()
    assert "2" in model.get_all_agents()


def test_build_model_requires_actions():
    """Test that Actions section is required."""
    toml_dict = {}
    with pytest.raises(ValueError, match="must contain.*Actions"):
        build_model(toml_dict)


def test_generate_complete_group_actions():
    """Test generating all complete group actions."""
    toml_dict = {
        "Actions": {"1": ["a", "b"], "2": ["c", "d"]},
    }
    model = build_model(toml_dict)

    cgas = model.generate_complete_group_actions()
    assert len(cgas) == 4

    actions_set = {
        frozenset(cga.actions.items())
        for cga in cgas
    }

    assert frozenset([("1", "a"), ("2", "c")]) in actions_set
    assert frozenset([("1", "a"), ("2", "d")]) in actions_set
    assert frozenset([("1", "b"), ("2", "c")]) in actions_set
    assert frozenset([("1", "b"), ("2", "d")]) in actions_set


# ============================================================================
# Test Pass 3: parse_queries() - parse formula strings
# ============================================================================

def test_parse_queries_basic():
    """Test parsing simple queries."""
    toml_dict = {
        "Actions": {"1": ["a"]},
        "Queries": {"Test": ["Xq", "[sd1]q"]},
    }
    model = build_model(toml_dict)
    model = parse_queries(model)

    assert len(model.queries) == 2

    assert model.queries[0].formula_ast is not None
    assert isinstance(model.queries[0].formula_ast, Next)
    assert isinstance(model.queries[0].formula_ast.formula, Prop)

    assert model.queries[1].formula_ast is not None
    assert isinstance(model.queries[1].formula_ast, PDLBox)


def test_parse_queries_modal_depth():
    """Test that modal depth is accessible after parsing."""
    toml_dict = {
        "Actions": {"1": ["a"]},
        "Queries": {"Test": ["q", "Xq", "XXq"]},
    }
    model = build_model(toml_dict)
    model = parse_queries(model)

    assert model.queries[0].modal_depth == 0  # q
    assert model.queries[1].modal_depth == 1  # Xq
    assert model.queries[2].modal_depth == 2  # XXq


def test_parse_queries_idempotent():
    """Test that parse_queries doesn't re-parse if already done."""
    toml_dict = {
        "Actions": {"1": ["a"]},
        "Queries": {"Test": ["Xq"]},
    }
    model = build_model(toml_dict)
    model = parse_queries(model)

    first_ast = model.queries[0].formula_ast
    model = parse_queries(model)
    assert model.queries[0].formula_ast is first_ast


def test_expand_queries_requires_parsed():
    """Test that expand_queries fails if queries not parsed."""
    toml_dict = {
        "Actions": {"1": ["a"]},
        "Queries": {"Test": ["Xq"]},
    }
    model = build_model(toml_dict)

    with pytest.raises(ValueError, match="not yet parsed"):
        expand_queries(model)


def test_model_max_modal_depth():
    """Test ALOModel.max_modal_depth() after pipeline."""
    toml_string = """
[Actions]
1 = ["a"]

[Queries]
Test = ["q", "Xq", "XXq", "X[a1]q"]
"""
    toml_dict = load_toml_string(toml_string)

    model = build_model(toml_dict)
    model = parse_queries(model)

    assert model.max_modal_depth() == 2


# ============================================================================
# Test error handling
# ============================================================================

def test_build_model_invalid_action_string():
    """Test that invalid action strings are caught."""
    toml_dict = {
        "Actions": {"1": ["sd"]},
        "Opposings": {"invalid": ["sd1"]},
    }

    with pytest.raises(ValueError, match="has no agent number"):
        build_model(toml_dict)


def test_parse_queries_invalid_syntax():
    """Test that malformed queries raise errors."""
    toml_dict = {
        "Actions": {"1": ["a"]},
        "Queries": {"Test": ["X(unclosed"]},
    }
    model = build_model(toml_dict)

    with pytest.raises(Exception):
        parse_queries(model)


def test_build_model_missing_actions():
    """Test error when Actions section missing."""
    toml_dict = {"Queries": {"Test": ["Xq"]}}

    with pytest.raises(ValueError, match="Actions"):
        build_model(toml_dict)


# ============================================================================
# Test roundtrip / data preservation
# ============================================================================

def test_pipeline_with_agent_groups():
    """Test parsing agent groups."""
    toml_string = """
[Actions]
1 = ["a"]
2 = ["b"]
3 = ["c"]

[AgentGroups]
Ag = [1, 2]
"""
    toml_dict = load_toml_string(toml_string)
    model = build_model(toml_dict)

    assert "Ag" in model.agent_groups
