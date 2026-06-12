"""Unit tests for formula expansion (Pass 4)."""

import pytest
from alo_translator.model.core import ALOModel, GroupAction
from alo_translator.model.formula import (
    Prop, DoAction, FreeDoAction, Negation, Conjunction, Disjunction,
    Implication, Biconditional, Box, Diamond, Next, Top, Bottom,
    PDLBox, PDLDiamond, ExpectedResult, ButFor, Ness,
    XSTIT, DXSTIT, PotentialResponsibility, StrongResponsibility, PlainResponsibility,
    IndividualAction, IndividualAgent,
)
from alo_translator.parsers.formula_expander import FormulaExpander, expand_formula


@pytest.fixture
def simple_model():
    """Create a simple 2-agent model for testing."""
    return ALOModel(
        agents_actions={
            "1": ["sd", "ha"],
            "2": ["ss", "ha"]
        }
    )


@pytest.fixture
def model_with_histories():
    """2-agent model with named histories — required for responsibility operator expansion."""
    model = ALOModel(
        agents_actions={
            "1": ["sd", "ha"],
            "2": ["ss", "ha"]
        }
    )
    model.named_histories = {
        "h1": GroupAction({"1": "sd", "2": "ss"}),
        "h2": GroupAction({"1": "sd", "2": "ha"}),
        "h3": GroupAction({"1": "ha", "2": "ss"}),
        "h4": GroupAction({"1": "ha", "2": "ha"}),
    }
    return model


# ============================================================================
# Primitives (pass through unchanged)
# ============================================================================

def test_expand_prop(simple_model):
    """Test that Prop passes through unchanged."""
    formula = Prop("q")
    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)
    assert expanded == Prop("q")


def test_expand_do_action(simple_model):
    """Test that DoAction passes through unchanged."""
    formula = DoAction(IndividualAction("sd", "1"))
    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)
    assert expanded == formula


def test_expand_free_do_action(simple_model):
    """Test that FreeDoAction passes through unchanged."""
    formula = FreeDoAction(IndividualAction("sd", "1"))
    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)
    assert expanded == formula


def test_expand_top_bottom(simple_model):
    """Test that Top and Bottom pass through unchanged."""
    expander = FormulaExpander(simple_model)
    assert expander.expand(Top()) == Top()
    assert expander.expand(Bottom()) == Bottom()


# ============================================================================
# Primitive operators (expand children only)
# ============================================================================

def test_expand_negation(simple_model):
    """Test that Negation expands its child."""
    formula = Negation(Prop("q"))
    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)
    assert expanded == Negation(Prop("q"))
    assert isinstance(expanded, Negation)
    assert expanded.formula == Prop("q")


def test_expand_conjunction(simple_model):
    """Test that Conjunction expands both children."""
    formula = Conjunction(Prop("p"), Prop("q"))
    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)
    assert expanded == Conjunction(Prop("p"), Prop("q"))


def test_expand_box(simple_model):
    """Test that Box expands its child."""
    formula = Box(Prop("q"))
    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)
    assert expanded == Box(Prop("q"))


def test_expand_next(simple_model):
    """Test that Next expands its child."""
    formula = Next(Prop("q"))
    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)
    assert expanded == Next(Prop("q"))


# ============================================================================
# Standard defined operators (optional expansion)
# ============================================================================

def test_expand_disjunction_no_expand_standard(simple_model):
    """Test that Disjunction is kept when expand_standard=False."""
    formula = Disjunction(Prop("p"), Prop("q"))
    expander = FormulaExpander(simple_model, expand_standard=False)
    expanded = expander.expand(formula)
    assert isinstance(expanded, Disjunction)
    assert expanded.left == Prop("p")
    assert expanded.right == Prop("q")


def test_expand_disjunction_with_expand_standard(simple_model):
    """Test that Disjunction is expanded when expand_standard=True."""
    formula = Disjunction(Prop("p"), Prop("q"))
    expander = FormulaExpander(simple_model, expand_standard=True)
    expanded = expander.expand(formula)
    # φ ∨ ψ → ¬(¬φ ∧ ¬ψ)
    assert isinstance(expanded, Negation)
    assert isinstance(expanded.formula, Conjunction)


def test_expand_implication_with_expand_standard(simple_model):
    """Test that Implication is expanded when expand_standard=True."""
    formula = Implication(Prop("p"), Prop("q"))
    expander = FormulaExpander(simple_model, expand_standard=True)
    expanded = expander.expand(formula)
    # φ → ψ ≡ ¬(φ ∧ ¬ψ)
    assert isinstance(expanded, Negation)
    assert isinstance(expanded.formula, Conjunction)


def test_expand_diamond_with_expand_standard(simple_model):
    """Test that Diamond is expanded when expand_standard=True."""
    formula = Diamond(Prop("q"))
    expander = FormulaExpander(simple_model, expand_standard=True)
    expanded = expander.expand(formula)
    # ◊φ → ¬□¬φ
    expected = Negation(Box(Negation(Prop("q"))))
    assert expanded == expected


# ============================================================================
# PDL-style operators
# ============================================================================

def test_expand_pdl_box(simple_model):
    """Test PDL-Box expansion: [a1]φ → □(do(a1) → Xφ)."""
    action = IndividualAction("sd", "1")
    formula = PDLBox(action, Prop("q"))
    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)

    assert isinstance(expanded, Box)
    assert isinstance(expanded.formula, Implication)
    assert expanded.formula.antecedent == DoAction(action)
    assert expanded.formula.consequent == Next(Prop("q"))


def test_expand_pdl_diamond(simple_model):
    """Test PDL-Diamond expansion: <a1>φ → ◊(do(a1) ∧ Xφ)."""
    action = IndividualAction("sd", "1")
    formula = PDLDiamond(action, Prop("q"))
    expander = FormulaExpander(simple_model, expand_standard=False)
    expanded = expander.expand(formula)

    assert isinstance(expanded, Diamond)
    assert isinstance(expanded.formula, Conjunction)
    assert expanded.formula.left == DoAction(action)
    assert expanded.formula.right == Next(Prop("q"))


def test_expand_expected_result(simple_model):
    """Test Expected Result expansion: do(a1) [+]-> φ → □(free_do(a1) → Xφ)."""
    action = IndividualAction("sd", "1")
    formula = ExpectedResult(action, Prop("q"))
    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)

    assert isinstance(expanded, Box)
    assert isinstance(expanded.formula, Implication)
    assert expanded.formula.antecedent == FreeDoAction(action)
    assert expanded.formula.consequent == Next(Prop("q"))


# ============================================================================
# STIT operators
# ============================================================================

def test_expand_xstit(simple_model):
    """Test XSTIT expansion: [1 xstit]φ → disjunction over agent's actions."""
    agent = IndividualAgent("1")
    formula = XSTIT(agent, Prop("q"))
    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)

    assert isinstance(expanded, Disjunction)
    if isinstance(expanded.left, Conjunction):
        assert isinstance(expanded.left.left, DoAction)


def test_expand_dxstit(simple_model):
    """Test DXSTIT expansion: [1 dxstit]φ → [1 xstit]φ ∧ ¬□Xφ."""
    agent = IndividualAgent("1")
    formula = DXSTIT(agent, Prop("q"))
    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)

    assert isinstance(expanded, Conjunction)
    assert isinstance(expanded.right, Negation)
    assert isinstance(expanded.right.formula, Box)


# ============================================================================
# Responsibility operators (require named_histories in model)
# ============================================================================

def test_expand_potential_responsibility(model_with_histories):
    """Test potential responsibility expansion."""
    agent = IndividualAgent("1")
    formula = PotentialResponsibility(agent, Prop("q"))
    expander = FormulaExpander(model_with_histories)
    expanded = expander.expand(formula)

    assert isinstance(expanded, Conjunction)


def test_expand_strong_responsibility(model_with_histories):
    """Test strong responsibility expansion."""
    agent = IndividualAgent("1")
    formula = StrongResponsibility(agent, Prop("q"))
    expander = FormulaExpander(model_with_histories)
    expanded = expander.expand(formula)

    # Disjunction when multiple histories match; Conjunction when only one does
    assert isinstance(expanded, (Disjunction, Conjunction))


def test_expand_plain_responsibility(model_with_histories):
    """Test plain responsibility expansion."""
    agent = IndividualAgent("1")
    formula = PlainResponsibility(agent, Prop("q"))
    expander = FormulaExpander(model_with_histories)
    expanded = expander.expand(formula)

    assert isinstance(expanded, (Disjunction, Conjunction))


# ============================================================================
# Causal operators
# ============================================================================

def test_expand_but_for(simple_model):
    """Test but-for expansion."""
    action = IndividualAction("sd", "1")
    formula = ButFor(action, Prop("q"))
    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)

    assert isinstance(expanded, Conjunction)
    assert isinstance(expanded.left, Next)
    assert expanded.left.formula == Prop("q")
    assert isinstance(expanded.right, (Disjunction, Conjunction, DoAction, Bottom))


def test_expand_ness(simple_model):
    """Test NESS expansion."""
    action = IndividualAction("sd", "1")
    formula = Ness(action, Prop("q"))
    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)

    assert expanded is not None
    assert isinstance(expanded, (Disjunction, Conjunction, Bottom))


# ============================================================================
# Modal depth preservation
# ============================================================================

def test_expansion_preserves_modal_depth_pdl_box(simple_model):
    """Test that PDL-Box expansion preserves modal depth."""
    action = IndividualAction("sd", "1")
    formula = PDLBox(action, Prop("q"))
    assert formula.modal_depth() == 1

    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)
    assert expanded.modal_depth() == 1


def test_expansion_preserves_modal_depth_expected_result(simple_model):
    """Test that Expected Result expansion preserves modal depth."""
    action = IndividualAction("sd", "1")
    formula = ExpectedResult(action, Prop("q"))
    assert formula.modal_depth() == 1

    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)
    assert expanded.modal_depth() == 1


def test_expansion_preserves_modal_depth_nested(simple_model):
    """Test modal depth preservation with nested operators."""
    action = IndividualAction("sd", "1")
    formula = PDLBox(action, Next(Prop("q")))
    assert formula.modal_depth() == 2

    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)
    assert expanded.modal_depth() == 2


# ============================================================================
# Recursive expansion
# ============================================================================

def test_recursive_expansion_conjunction_with_pdl(simple_model):
    """Test that expansion works recursively through boolean operators."""
    action = IndividualAction("sd", "1")
    formula = Conjunction(
        PDLBox(action, Prop("p")),
        PDLBox(action, Prop("q"))
    )

    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)

    assert isinstance(expanded, Conjunction)
    assert isinstance(expanded.left, Box)
    assert isinstance(expanded.right, Box)


def test_recursive_expansion_negation_of_pdl(simple_model):
    """Test expansion of negated PDL box."""
    action = IndividualAction("sd", "1")
    formula = Negation(PDLBox(action, Prop("q")))

    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)

    assert isinstance(expanded, Negation)
    assert isinstance(expanded.formula, Box)


# ============================================================================
# Convenience function
# ============================================================================

def test_expand_formula_convenience_function(simple_model):
    """Test the convenience function works."""
    action = IndividualAction("sd", "1")
    formula = PDLBox(action, Prop("q"))

    expanded = expand_formula(formula, simple_model)

    assert isinstance(expanded, Box)
    assert expanded.modal_depth() == 1


def test_expand_formula_with_standard_expansion(simple_model):
    """Test convenience function with standard expansion enabled."""
    formula = Disjunction(Prop("p"), Prop("q"))

    expanded = expand_formula(formula, simple_model, expand_standard=True)

    assert isinstance(expanded, Negation)


# ============================================================================
# Edge cases
# ============================================================================

def test_expand_deeply_nested_formula(simple_model):
    """Test expansion of deeply nested formula."""
    action = IndividualAction("sd", "1")
    formula = Box(PDLBox(action, Next(Prop("q"))))

    expander = FormulaExpander(simple_model)
    expanded = expander.expand(formula)

    assert isinstance(expanded, Box)
    assert isinstance(expanded.formula, Box)


def test_expand_empty_actions():
    """Test XSTIT expansion when agent has no actions."""
    model = ALOModel(agents_actions={"1": ["sd"]})
    agent = IndividualAgent("3")  # Agent not in model
    formula = XSTIT(agent, Prop("q"))

    expander = FormulaExpander(model)
    expanded = expander.expand(formula)

    assert isinstance(expanded, Bottom)
