"""Unit tests for formula parser (Pass 3: TOML → dict → ALOModel → parsed queries)."""

import pytest
from alo_translator.parsers.formula_parser import parse_formula
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
# Basic Atoms and Operators
# ============================================================================

def test_parse_prop():
    """Test parsing propositional atom."""
    ast = parse_formula("q")
    assert ast == Prop("q")


def test_parse_top():
    """Test parsing top (tautology)."""
    ast = parse_formula("T")
    assert ast == Top()


def test_parse_bottom():
    """Test parsing bottom (contradiction)."""
    ast = parse_formula("_L")
    assert ast == Bottom()


def test_parse_negation():
    """Test parsing negation."""
    ast = parse_formula("~q")
    assert ast == Negation(Prop("q"))


def test_parse_conjunction():
    """Test parsing conjunction."""
    ast = parse_formula("p & q")
    assert ast == Conjunction(Prop("p"), Prop("q"))


def test_parse_disjunction():
    """Test parsing disjunction with 'v'."""
    ast = parse_formula("p v q")
    assert ast == Disjunction(Prop("p"), Prop("q"))


def test_parse_implication():
    """Test parsing implication."""
    ast = parse_formula("p -> q")
    assert ast == Implication(Prop("p"), Prop("q"))


def test_parse_biconditional():
    """Test parsing biconditional."""
    ast = parse_formula("p <-> q")
    assert ast == Biconditional(Prop("p"), Prop("q"))


# ============================================================================
# Primitive Modal Operators
# ============================================================================

def test_parse_next():
    """Test parsing Next operator."""
    ast = parse_formula("Xq")
    assert ast == Next(Prop("q"))


def test_parse_box():
    """Test parsing Box operator."""
    ast = parse_formula("[]q")
    assert ast == Box(Prop("q"))


def test_parse_diamond():
    """Test parsing Diamond operator."""
    ast = parse_formula("<>q")
    assert ast == Diamond(Prop("q"))


# ============================================================================
# Action Expressions
# ============================================================================

def test_parse_individual_action():
    """Test parsing individual action in do()."""
    ast = parse_formula("do(sd1)")
    assert ast == DoAction(IndividualAction("sd", "1"))


def test_parse_group_action_colon_syntax():
    """Test parsing group action with colon syntax."""
    ast = parse_formula("do({1:sd, 2:ss})")
    expected = DoAction(GroupAction({"1": "sd", "2": "ss"}))
    assert ast == expected


def test_parse_group_action_combined_syntax():
    """Test parsing group action with combined identifiers."""
    ast = parse_formula("do({sd1, ss2})")
    expected = DoAction(GroupAction({"1": "sd", "2": "ss"}))
    assert ast == expected


def test_parse_free_do_action():
    """Test parsing free_do action."""
    ast = parse_formula("free_do(sd1)")
    assert ast == FreeDoAction(IndividualAction("sd", "1"))


def test_parse_opposing():
    """Test parsing opposing relation."""
    ast = parse_formula("sd1 |> ha2")
    expected = Opposing(IndividualAction("sd", "1"), IndividualAction("ha", "2"))
    assert ast == expected


# ============================================================================
# PDL-style Modalities
# ============================================================================

def test_parse_pdl_box():
    """Test parsing PDL box: [a]φ."""
    ast = parse_formula("[sd1]q")
    assert ast == PDLBox(IndividualAction("sd", "1"), Prop("q"))


def test_parse_pdl_diamond():
    """Test parsing PDL diamond: <a>φ."""
    ast = parse_formula("<sd1>q")
    assert ast == PDLDiamond(IndividualAction("sd", "1"), Prop("q"))


def test_parse_pdl_box_with_negation():
    """Test parsing PDL box with negated formula."""
    ast = parse_formula("[sd1]~q")
    assert ast == PDLBox(IndividualAction("sd", "1"), Negation(Prop("q")))


# ============================================================================
# Causal Operators
# ============================================================================

def test_parse_expected_result():
    """Test parsing expected result: do(a) [+]-> φ."""
    ast = parse_formula("do(sd1) [+]-> q")
    expected = ExpectedResult(IndividualAction("sd", "1"), Prop("q"))
    assert ast == expected


def test_parse_but_for():
    """Test parsing but-for causation."""
    ast = parse_formula("but(sd1, q)")
    expected = ButFor(IndividualAction("sd", "1"), Prop("q"))
    assert ast == expected


def test_parse_ness():
    """Test parsing NESS causation."""
    ast = parse_formula("ness(sd1, q)")
    expected = Ness(IndividualAction("sd", "1"), Prop("q"))
    assert ast == expected


# ============================================================================
# STIT Operators
# ============================================================================

def test_parse_xstit():
    """Test parsing XSTIT."""
    ast = parse_formula("[1 XSTIT]q")
    assert ast == XSTIT(IndividualAgent("1"), Prop("q"))


def test_parse_dxstit():
    """Test parsing deliberative XSTIT."""
    ast = parse_formula("[1 DXSTIT]q")
    assert ast == DXSTIT(IndividualAgent("1"), Prop("q"))


# ============================================================================
# Responsibility Operators
# ============================================================================

def test_parse_potential_responsibility():
    """Test parsing potential responsibility."""
    ast = parse_formula("[1 pres]q")
    assert ast == PotentialResponsibility(IndividualAgent("1"), Prop("q"))


def test_parse_strong_responsibility():
    """Test parsing strong responsibility."""
    ast = parse_formula("[1 sres]q")
    assert ast == StrongResponsibility(IndividualAgent("1"), Prop("q"))


def test_parse_plain_responsibility():
    """Test parsing plain responsibility."""
    ast = parse_formula("[1 res]q")
    assert ast == PlainResponsibility(IndividualAgent("1"), Prop("q"))


def test_parse_responsibility_with_agent_group():
    """Test parsing responsibility with agent group."""
    ast = parse_formula("[{1, 2} pres]q")
    expected = PotentialResponsibility(AgentGroup(["1", "2"]), Prop("q"))
    assert ast == expected


def test_parse_responsibility_with_named_group():
    """Test parsing responsibility with named agent group."""
    ast = parse_formula("[Ag pres]q")
    expected = PotentialResponsibility(NamedAgentGroup("Ag"), Prop("q"))
    assert ast == expected


# ============================================================================
# Complex Nested Formulae
# ============================================================================

def test_parse_nested_next():
    """Test parsing nested Next: XXq."""
    ast = parse_formula("XXq")
    assert ast == Next(Next(Prop("q")))


def test_parse_conjunction_with_next():
    """Test parsing conjunction with Next: p & Xq."""
    ast = parse_formula("p & Xq")
    expected = Conjunction(Prop("p"), Next(Prop("q")))
    assert ast == expected


def test_parse_disjunction_with_next():
    """Test parsing disjunction with Next: Xp v Xq."""
    ast = parse_formula("Xp v Xq")
    expected = Disjunction(Next(Prop("p")), Next(Prop("q")))
    assert ast == expected


def test_parse_implication_with_pdl():
    """Test parsing implication with PDL box: [sd1]p -> q."""
    ast = parse_formula("[sd1]p -> q")
    expected = Implication(PDLBox(IndividualAction("sd", "1"), Prop("p")), Prop("q"))
    assert ast == expected


def test_parse_negated_conjunction():
    """Test parsing negated conjunction: ~(p & q)."""
    ast = parse_formula("~(p & q)")
    expected = Negation(Conjunction(Prop("p"), Prop("q")))
    assert ast == expected


def test_parse_complex_causal():
    """Test parsing complex causal formula: but(sd1, q) & [1 pres]q."""
    ast = parse_formula("but(sd1, q) & [1 pres]q")
    expected = Conjunction(
        ButFor(IndividualAction("sd", "1"), Prop("q")),
        PotentialResponsibility(IndividualAgent("1"), Prop("q"))
    )
    assert ast == expected


def test_parse_box_with_next():
    """Test parsing box with next: []Xq."""
    ast = parse_formula("[]Xq")
    assert ast == Box(Next(Prop("q")))


def test_parse_next_with_pdl_box():
    """Test parsing next with PDL box: X[sd1]q."""
    ast = parse_formula("X[sd1]q")
    expected = Next(PDLBox(IndividualAction("sd", "1"), Prop("q")))
    assert ast == expected


# ============================================================================
# Operator Precedence
# ============================================================================

def test_precedence_negation_over_conjunction():
    """Test that negation binds tighter than conjunction: ~p & q = (~p) & q."""
    ast = parse_formula("~p & q")
    expected = Conjunction(Negation(Prop("p")), Prop("q"))
    assert ast == expected


def test_precedence_conjunction_over_disjunction():
    """Test that conjunction binds tighter than disjunction: p v q & r = p v (q & r)."""
    ast = parse_formula("p v q & r")
    expected = Disjunction(Prop("p"), Conjunction(Prop("q"), Prop("r")))
    assert ast == expected


def test_precedence_disjunction_over_implication():
    """Test that disjunction binds tighter than implication: p -> q v r = p -> (q v r)."""
    ast = parse_formula("p -> q v r")
    expected = Implication(Prop("p"), Disjunction(Prop("q"), Prop("r")))
    assert ast == expected


def test_precedence_with_parentheses():
    """Test that parentheses override precedence: (p v q) & r."""
    ast = parse_formula("(p v q) & r")
    expected = Conjunction(Disjunction(Prop("p"), Prop("q")), Prop("r"))
    assert ast == expected


# ============================================================================
# Associativity
# ============================================================================

def test_conjunction_left_associative():
    """Test that conjunction is left-associative: p & q & r = (p & q) & r."""
    ast = parse_formula("p & q & r")
    expected = Conjunction(Conjunction(Prop("p"), Prop("q")), Prop("r"))
    assert ast == expected


def test_disjunction_left_associative():
    """Test that disjunction is left-associative: p v q v r = (p v q) v r."""
    ast = parse_formula("p v q v r")
    expected = Disjunction(Disjunction(Prop("p"), Prop("q")), Prop("r"))
    assert ast == expected


def test_implication_right_associative():
    """Test that implication is right-associative: p -> q -> r = p -> (q -> r)."""
    ast = parse_formula("p -> q -> r")
    expected = Implication(Prop("p"), Implication(Prop("q"), Prop("r")))
    assert ast == expected


# ============================================================================
# Modal Depth Verification
# ============================================================================

def test_parsed_modal_depth_simple():
    """Test that parsed AST has correct modal depth: Xq."""
    ast = parse_formula("Xq")
    assert ast.modal_depth() == 1


def test_parsed_modal_depth_pdl():
    """Test modal depth of PDL box: [sd1]q."""
    ast = parse_formula("[sd1]q")
    assert ast.modal_depth() == 1


def test_parsed_modal_depth_expected_result():
    """Test modal depth of expected result: do(sd1) [+]-> q."""
    ast = parse_formula("do(sd1) [+]-> q")
    assert ast.modal_depth() == 1


def test_parsed_modal_depth_responsibility():
    """Test modal depth of responsibility: [1 pres]q."""
    ast = parse_formula("[1 pres]q")
    assert ast.modal_depth() == 1


def test_parsed_modal_depth_complex():
    """Test modal depth of complex formula: X[sd1]Xq."""
    ast = parse_formula("X[sd1]Xq")
    # X adds 1, [sd1] adds 1, X adds 1 = 3 total
    assert ast.modal_depth() == 3


# ============================================================================
# Error Handling
# ============================================================================

def test_parse_invalid_syntax():
    """Test that invalid syntax raises an error."""
    with pytest.raises(Exception):  # Lark will raise LarkError or similar
        parse_formula("Xq & ")  # Missing right operand


def test_parse_invalid_action_format():
    """Test that invalid action format raises an error."""
    with pytest.raises(ValueError, match="Invalid action format"):
        parse_formula("do(invalid)")  # No number in action


def test_parse_empty_string():
    """Test that empty string raises an error."""
    with pytest.raises(Exception):
        parse_formula("")


# ============================================================================
# Structural Equality After Parsing
# ============================================================================

def test_parsed_equality():
    """Test that parsing the same formula twice produces equal ASTs."""
    ast1 = parse_formula("Xq")
    ast2 = parse_formula("Xq")
    assert ast1 == ast2


def test_parsed_inequality():
    """Test that different formulae produce different ASTs."""
    ast1 = parse_formula("Xq")
    ast2 = parse_formula("Xp")
    assert ast1 != ast2


def test_parsed_structural_equality():
    """Test structural equality of complex formulae."""
    ast1 = parse_formula("(p & Xq) v [sd1]r")
    ast2 = parse_formula("(p & Xq) v [sd1]r")
    assert ast1 == ast2


# ============================================================================
# Real-World Query Examples
# ============================================================================

def test_parse_alice_shoots_dan():
    """Test parsing: Dan dies after Alice shoots (Next proposition)."""
    ast = parse_formula("Xq")
    assert isinstance(ast, Next)
    assert isinstance(ast.formula, Prop)
    assert ast.formula.symbol == "q"


def test_parse_expected_effect():
    """Test parsing: Expected result of Alice shooting Dan."""
    ast = parse_formula("do(sd1) [+]-> q")
    assert isinstance(ast, ExpectedResult)
    assert ast.action == IndividualAction("sd", "1")
    assert ast.formula == Prop("q")


def test_parse_responsibility_alice():
    """Test parsing: Alice potentially responsible for Dan's death."""
    ast = parse_formula("[1 pres]q")
    assert isinstance(ast, PotentialResponsibility)
    assert ast.agent == IndividualAgent("1")
    assert ast.formula == Prop("q")


def test_parse_joint_action():
    """Test parsing: Joint action by two agents."""
    ast = parse_formula("do({1:sd, 2:ss})")
    assert isinstance(ast, DoAction)
    assert isinstance(ast.action, GroupAction)
    assert ast.action.actions == {"1": "sd", "2": "ss"}
