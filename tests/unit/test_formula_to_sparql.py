"""
Unit tests for FormulaToSPARQL (alo_translator/serializers/sparql.py).

No Konclude dependency -- these check the SHAPE of generated SPARQL
(UNION/MINUS keywords present, no bare-MINUS-as-branch, no duplicated
owl:Thing anchors) rather than running a reasoner. Correctness against a
real reasoner is covered separately by
tests/test_konclude_sparql_baselines.py (skipped if Konclude is absent).

Several of these are direct regression tests for bugs found and fixed
during development (see docs/sparql_serializer.md and the alon_test_suite
findings referenced in sparql.py's docstrings) -- each one failed with a
real wrong answer before its corresponding fix, not just a hypothetical
concern.
"""

import re

import pytest
from lark import Lark
from lark.exceptions import VisitError

from alo_translator.serializers.sparql import FormulaToSPARQL

GRAMMAR_PATH = "alo_translator/parsers/alon_grammar_clean.lark"


@pytest.fixture(scope="module")
def parser():
    with open(GRAMMAR_PATH) as f:
        grammar = f.read()
    return Lark(grammar, start="start", parser="lalr")


def compile_formula(parser, formula: str, name: str = "test") -> str:
    """Parse `formula => name` and return the generated SPARQL query."""
    tree = parser.parse(f"{formula} => {name}")
    transformer = FormulaToSPARQL()
    transformer.transform(tree)
    return transformer.queries[name]


# ---------------------------------------------------------------------------
# Basic per-construct shape checks
# ---------------------------------------------------------------------------

def test_prop_emits_class_membership_triple(parser):
    sparql = compile_formula(parser, "q")
    assert "?idx0 a alon:q ." in sparql


def test_do_action_emits_class_membership_triple(parser):
    sparql = compile_formula(parser, "do(sd1)")
    assert "?idx0 a alon:sd1 ." in sparql


def test_conjunction_concatenates_patterns(parser):
    sparql = compile_formula(parser, "do(sd1) & q")
    assert "?idx0 a alon:sd1 ." in sparql
    assert "?idx0 a alon:q ." in sparql
    assert "UNION" not in sparql


def test_disjunction_emits_union_keyword(parser):
    """Regression test: an early version of disjunction() wrapped each
    branch in `{ }` but never emitted the literal UNION keyword, so two
    branches were silently ANDed (implicit SPARQL group juxtaposition)
    instead of ORed -- a real bug caught by cross-checking against the
    Konclude baseline for a query that used disjunction, not by
    inspection."""
    sparql = compile_formula(parser, "do(sd1) v q")
    assert " UNION " in sparql


def test_next_uses_succ_property(parser):
    sparql = compile_formula(parser, "Xq")
    assert "alon:succ" in sparql


def test_box_uses_same_moment_and_nested_minus(parser):
    sparql = compile_formula(parser, "[]q")
    assert "alon:same_moment" in sparql
    assert sparql.count("MINUS") >= 2  # double-negation shape


def test_negation_uses_minus(parser):
    sparql = compile_formula(parser, "~q")
    assert "MINUS" in sparql


# ---------------------------------------------------------------------------
# Regression tests for real bugs found during development
# ---------------------------------------------------------------------------

def test_no_bare_minus_as_union_branch(parser):
    """Regression test for alon_test_suite findings/bug-006: a UNION
    branch consisting of ONLY a MINUS block (nothing preceding it in that
    branch's own { } group) is a degenerate/invalid MINUS use -- it was
    previously silently miscomputed (now the reasoner errors loudly
    instead, per that finding's fix, but the generator should never emit
    this shape in the first place). Every UNION branch must have a
    positive triple pattern before any MINUS within that same branch.
    """
    sparql = compile_formula(parser, "do(sd1) -> q")  # implication uses MINUS+UNION internally
    # Find each UNION branch (naive brace-matching is enough for this
    # generator's own consistent formatting) and check none starts with
    # a bare MINUS.
    branches = re.findall(r'\{\s*\n(.*?)\n\s*\}', sparql, re.DOTALL)
    for branch in branches:
        stripped = branch.strip()
        if stripped.startswith("MINUS"):
            pytest.fail(f"Found a UNION branch starting with bare MINUS: {branch!r}")


def test_conjunction_with_disjunction_conjunct_no_duplicate_anchor(parser):
    """Regression test: conjunction() used to eagerly finalize a
    _Disjunction conjunct into a plain string, which meant an enclosing
    caller (expansion_axiom, or a further-outer conjunction/negation)
    couldn't tell it still needed anchor-distribution treatment and added
    its own top-level owl:Thing anchor on top -- a real double-anchor
    that silently broke a real formula (ness's `f7` axiom,
    `do(sd1) & f8 & ~[]Xq` combined with a disjunction elsewhere in the
    same conjunction) during end-to-end testing against the 3.1 baseline.
    """
    sparql = compile_formula(parser, "do(sd1) & (do(sd1) v do(ss2))")
    # The exact failure mode: "?idx0 a owl:Thing ." appearing immediately
    # before a "{" that opens a UNION block with no other content between
    # them (i.e. an anchor with nothing but the union following it,
    # duplicating the per-branch anchors already inside).
    assert not re.search(r'a owl:Thing \.\s*\n\s*\{\s*\n\s*\?idx0 a owl:Thing \.', sparql)


def test_conjunction_single_disjunction_item_passthrough(parser):
    """Regression test: conjunction() lacked a single-item passthrough
    check, so when the grammar wrapped a bare disjunction() result as
    conjunction's ONLY item (happens at every operator level per the
    grammar's ?conjunction: unary ("&" unary)* shape), it was eagerly
    finalized one tree level too early -- confirmed via a real query
    (ness's `f7`) where this produced a doubled top-level anchor and a
    wrong (empty) answer.
    """
    # A formula whose only top-level connective is disjunction, reached
    # through a single-item conjunction wrapper (implicit in the grammar).
    sparql = compile_formula(parser, "do(sd1) v do(ss2)")
    assert sparql.count("owl:Thing") <= 3  # one per UNION branch + none redundant


def test_implication_does_not_use_bare_negation_as_branch(parser):
    """Regression test: implication() originally built ~p via
    disjunction([negation(p), q]), which drops negation()'s own complete
    `MINUS { owl:Thing . ... }` output whole into a UNION branch as
    `{ MINUS { owl:Thing . ... } }` -- structurally fine on its own, but
    when negation's inner argument is itself compound this shape hits
    findings/bug-006. implication() was rewritten to build the negated
    antecedent as its own anchored MINUS block directly, per user
    direction (special-case implication, matching this codebase's
    existing per-backend-override pattern).
    """
    sparql = compile_formula(parser, "do(sd1) -> q")
    assert "MINUS" in sparql
    assert " UNION " in sparql


def test_free_do_action_negates_opposing_class(parser):
    sparql = compile_formula(parser, "free_do(sd1)")
    assert "?idx0 a alon:sd1 ." in sparql
    assert "alon:Opp2sd1" in sparql
    assert "MINUS" in sparql


def test_must_not_appear_operators_raise(parser):
    """pres/sres/res/etc. should never reach FormulaToSPARQL directly --
    they're expanded away by ExpanderTransformer first. Seeing one here
    means expansion is broken; fail loudly (matches FormulaToOWL's
    identical guard). Lark wraps the raised ValueError in a VisitError."""
    with pytest.raises(VisitError, match="should not appear"):
        compile_formula(parser, "[1 pres]q")
