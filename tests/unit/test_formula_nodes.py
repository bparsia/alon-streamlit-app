"""Unit tests for FormulaNode IR classes and modal_depth() methods."""

import pytest
from alo_translator.model.formula import (
    # Primitives
    Prop, DoAction, FreeDoAction, Opposing, Negation, Conjunction, Box, Next,
    # Standard defined
    Disjunction, Implication, Biconditional, Diamond, Top, Bottom,
    # ALOn-specific defined
    PDLBox, PDLDiamond, ExpectedResult, ButFor, Ness,
    XSTIT, DXSTIT, PotentialResponsibility, StrongResponsibility, PlainResponsibility,
    # Action/Agent types
    IndividualAction, GroupAction, IndividualAgent, AgentGroup, NamedAgentGroup,
)


# ============================================================================
# Primitive FormulaNode Tests
# ============================================================================

@pytest.mark.parametrize("node,expected_depth", [
    # Primitives with depth 0
    (Prop("q"), 0),
    (DoAction(IndividualAction("sd", "1")), 0),
    (FreeDoAction(IndividualAction("sd", "1")), 0),
    (Opposing(IndividualAction("sd", "1"), IndividualAction("ha", "2")), 0),
    (Top(), 0),
    (Bottom(), 0),
    # Next adds 1
    (Next(Prop("q")), 1),
    (Next(Next(Prop("q"))), 2),
    (Next(Next(Next(Prop("q")))), 3),
    # Box/Diamond/Negation inherit depth
    (Box(Prop("q")), 0),
    (Diamond(Prop("q")), 0),
    (Negation(Prop("q")), 0),
    (Box(Next(Prop("q"))), 1),
    (Negation(Next(Prop("q"))), 1),
    # Conjunction/Disjunction take max
    (Conjunction(Prop("p"), Prop("q")), 0),
    (Conjunction(Next(Prop("p")), Prop("q")), 1),
    (Conjunction(Next(Prop("p")), Next(Prop("q"))), 1),
    (Disjunction(Next(Prop("p")), Next(Next(Prop("q")))), 2),
])
def test_modal_depth_primitives(node, expected_depth):
    """Test modal depth calculation for primitive and standard operators."""
    assert node.modal_depth() == expected_depth


# ============================================================================
# ALOn-Specific FormulaNode Tests  
# ============================================================================

@pytest.mark.parametrize("node,expected_depth", [
    # ALOn operators add 1 (hidden X)
    (PDLBox(IndividualAction("sd", "1"), Prop("q")), 1),
    (PDLDiamond(IndividualAction("sd", "1"), Prop("q")), 1),
    (ExpectedResult(IndividualAction("sd", "1"), Prop("q")), 1),
    (ButFor(IndividualAction("sd", "1"), Prop("q")), 1),
    (Ness(IndividualAction("sd", "1"), Prop("q")), 1),
    (PotentialResponsibility(IndividualAgent("1"), Prop("q")), 1),
    (StrongResponsibility(IndividualAgent("1"), Prop("q")), 1),
    (PlainResponsibility(IndividualAgent("1"), Prop("q")), 1),
    # Nested: formula depth + 1
    (PDLBox(IndividualAction("sd", "1"), Next(Prop("q"))), 2),
    (ExpectedResult(IndividualAction("sd", "1"), Next(Prop("q"))), 2),
    (PotentialResponsibility(IndividualAgent("1"), Next(Prop("q"))), 2),
    # Next outside ALOn operator
    (Next(PDLBox(IndividualAction("sd", "1"), Prop("q"))), 2),
    (Next(ExpectedResult(IndividualAction("sd", "1"), Prop("q"))), 2),
])
def test_modal_depth_alon(node, expected_depth):
    """Test modal depth for ALOn-specific operators (all have hidden X)."""
    assert node.modal_depth() == expected_depth


# ============================================================================
# Structural Equality Tests
# ============================================================================

def test_prop_equality():
    """Test Prop structural equality."""
    assert Prop("q") == Prop("q")
    assert Prop("q") != Prop("p")
    assert Prop("q") != Next(Prop("q"))


def test_next_equality():
    """Test Next structural equality."""
    assert Next(Prop("q")) == Next(Prop("q"))
    assert Next(Prop("q")) != Next(Prop("p"))
    assert Next(Next(Prop("q"))) == Next(Next(Prop("q")))
    assert Next(Prop("q")) != Next(Next(Prop("q")))


def test_conjunction_equality():
    """Test Conjunction structural equality."""
    assert Conjunction(Prop("p"), Prop("q")) == Conjunction(Prop("p"), Prop("q"))
    assert Conjunction(Prop("p"), Prop("q")) != Conjunction(Prop("q"), Prop("p"))


def test_pdl_box_equality():
    """Test PDLBox structural equality."""
    action = IndividualAction("sd", "1")
    assert PDLBox(action, Prop("q")) == PDLBox(action, Prop("q"))
    assert PDLBox(action, Prop("q")) != PDLBox(action, Prop("p"))


def test_expected_result_equality():
    """Test ExpectedResult structural equality."""
    action = IndividualAction("sd", "1")
    assert ExpectedResult(action, Prop("q")) == ExpectedResult(action, Prop("q"))
    assert ExpectedResult(action, Prop("q")) != PDLBox(action, Prop("q"))


def test_complex_equality():
    """Test complex nested formula equality."""
    # ~([sd1]q v Xp)
    formula1 = Negation(
        Disjunction(
            PDLBox(IndividualAction("sd", "1"), Prop("q")),
            Next(Prop("p"))
        )
    )
    formula2 = Negation(
        Disjunction(
            PDLBox(IndividualAction("sd", "1"), Prop("q")),
            Next(Prop("p"))
        )
    )
    formula3 = Negation(
        Disjunction(
            PDLBox(IndividualAction("sd", "1"), Prop("p")),  # Different!
            Next(Prop("p"))
        )
    )
    
    assert formula1 == formula2
    assert formula1 != formula3


# ============================================================================
# String Representation Tests
# ============================================================================

def test_formula_str():
    """Test __str__ methods produce readable output."""
    assert str(Prop("q")) == "q"
    assert str(Next(Prop("q"))) == "Xq"
    assert str(Negation(Prop("q"))) == "~q"
    assert str(DoAction(IndividualAction("sd", "1"))) == "do(sd1)"
    assert str(FreeDoAction(IndividualAction("sd", "1"))) == "free_do(sd1)"


# ============================================================================
# Action/Agent Type Tests
# ============================================================================

def test_individual_action():
    """Test IndividualAction creation and string representation."""
    action = IndividualAction("sd", "1")
    assert str(action) == "sd1"
    assert action.action_type == "sd"
    assert action.agent == "1"


def test_group_action():
    """Test GroupAction creation and conversion."""
    action = GroupAction({"1": "sd", "2": "ss"})
    individual = action.to_individual_actions()
    
    assert len(individual) == 2
    assert IndividualAction("sd", "1") in individual
    assert IndividualAction("ss", "2") in individual


def test_action_types_in_formula():
    """Test that Action types work in FormulaNode."""
    # Individual action
    node1 = DoAction(IndividualAction("sd", "1"))
    assert node1.modal_depth() == 0
    
    # Group action  
    node2 = DoAction(GroupAction({"1": "sd", "2": "ss"}))
    assert node2.modal_depth() == 0


def test_agent_types():
    """Test Agent type variants."""
    # Individual agent
    agent1 = IndividualAgent("1")
    assert str(agent1) == "1"
    
    # Agent group
    agent2 = AgentGroup(["1", "2"])
    assert "{" in str(agent2)
    
    # Named agent group
    agent3 = NamedAgentGroup("Ag")
    assert str(agent3) == "Ag"


def test_agent_types_in_formula():
    """Test that Agent types work in FormulaNode."""
    # Individual agent
    node1 = PotentialResponsibility(IndividualAgent("1"), Prop("q"))
    assert node1.modal_depth() == 1
    
    # Agent group
    node2 = PotentialResponsibility(AgentGroup(["1", "2"]), Prop("q"))
    assert node2.modal_depth() == 1
    
    # Named group
    node3 = PotentialResponsibility(NamedAgentGroup("Ag"), Prop("q"))
    assert node3.modal_depth() == 1


# ============================================================================
# Complex Composition Tests
# ============================================================================

def test_complex_modal_depth_calculation():
    """Test modal depth on complex nested formulae."""
    # ~([sd1]q v Xp) should have max(1, 1) = 1
    formula = Negation(
        Disjunction(
            PDLBox(IndividualAction("sd", "1"), Prop("q")),
            Next(Prop("p"))
        )
    )
    assert formula.modal_depth() == 1


def test_expected_result_vs_pdl_box():
    """Verify ExpectedResult and PDLBox are different despite similar depth."""
    action = IndividualAction("sd", "1")
    expected = ExpectedResult(action, Prop("q"))
    pdl = PDLBox(action, Prop("q"))
    
    # Same modal depth
    assert expected.modal_depth() == pdl.modal_depth() == 1
    
    # But different nodes
    assert expected != pdl
    assert str(expected) != str(pdl)


def test_responsibility_operators_distinct():
    """Verify responsibility operators are distinct types."""
    agent = IndividualAgent("1")
    formula = Prop("q")
    
    pres = PotentialResponsibility(agent, formula)
    sres = StrongResponsibility(agent, formula)
    res = PlainResponsibility(agent, formula)
    
    # All have same depth
    assert pres.modal_depth() == sres.modal_depth() == res.modal_depth() == 1
    
    # But are different
    assert pres != sres != res
    assert pres != res


def test_provenance_tracking():
    """Test that provenance can be set and retrieved."""
    node = PDLBox(IndividualAction("sd", "1"), Prop("q"), provenance="test_source")
    assert node.provenance == "test_source"
    
    # Provenance doesn't affect equality
    node2 = PDLBox(IndividualAction("sd", "1"), Prop("q"), provenance="other_source")
    assert node == node2  # Structural equality ignores provenance


# ============================================================================
# Edge Cases
# ============================================================================

def test_deeply_nested_next():
    """Test that deeply nested Next operators correctly accumulate depth."""
    formula = Prop("q")
    for i in range(1, 6):
        formula = Next(formula)
        assert formula.modal_depth() == i


def test_mixed_operators_max_depth():
    """Test that binary operators correctly compute max depth."""
    # (Xp & XXq) should have depth = max(1, 2) = 2
    formula = Conjunction(
        Next(Prop("p")),
        Next(Next(Prop("q")))
    )
    assert formula.modal_depth() == 2


def test_all_operators_support_arbitrary_formulae():
    """Verify operators can be applied to arbitrary FormulaNode types."""
    # These should all construct without error
    formulas = [
        Negation(PDLBox(IndividualAction("a", "1"), Prop("q"))),
        Next(ExpectedResult(IndividualAction("a", "1"), Prop("q"))),
        Box(PotentialResponsibility(IndividualAgent("1"), Prop("q"))),
        Disjunction(ButFor(IndividualAction("a", "1"), Prop("q")), Next(Prop("p"))),
    ]
    
    # All should have valid modal depth
    for formula in formulas:
        depth = formula.modal_depth()
        assert isinstance(depth, int)
        assert depth >= 0
