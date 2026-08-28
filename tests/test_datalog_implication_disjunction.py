"""
Regression tests for a fix to FormulaToDatalog.implication/disjunction/
biconditional (alo_translator/serializers/datalog.py).

Bug (found 2026-08-28, see project_datalog_implication_disjunction_bug
memory): implication/disjunction previously raised ValueError whenever a
formula's top-level connective was `->` or `v` -- their error messages
claimed PyDatalogExpanderTransformer eliminates these first, but nothing
in the pipeline actually does that (ExpanderTransformer/
PyDatalogExpanderTransformer never override implication/disjunction; both
fall through to AlonTransformer's plain string roundtrip). The exception
was caught in DatalogIndexSerializer._generate_query_rules and silently
downgraded to a `# ERROR ...` comment -- the query just went missing from
generated output, no crash surfaced to any caller.

Root cause: pyDatalog's `|` operator does not work between rule-body Query
objects (confirmed directly: `p(X) | q(X)` raises TypeError). Fix: real
Datalog disjunction requires splitting into multiple rules sharing one
fresh helper predicate head (standard Datalog style), not a single `|`
expression -- mirrors the pre-existing box()/next() helper-rule pattern in
the same file. implication (p -> q == ~p v q) and biconditional
((p -> q) & (q -> p)) now delegate to the fixed disjunction.

Scope note: this fix is about ordinary point-wise model-checking
(evaluate/res_analyse), which is closed-world/per-index -- computing
whether a formula holds against one already-fully-specified finite model.
It has no bearing on, and cannot be made equivalent to, `background`'s
open-world/satisfiability semantics (checking whether ANY model of a set
of universally-quantified constraints exists) -- that's exactly why
DatalogIndexSerializer still raises immediately if model.background is
non-empty, untouched by this fix. See test_background_theory.py.

Run with:
  pytest tests/test_datalog_implication_disjunction.py -v
"""

from pathlib import Path

import pytest

from alo_translator.model.core import Query
from alo_translator.parsers.builder import parse_formula
from alo_translator.parsers.dbt_parser import parse_dbt_diagram
from alo_translator.query_generation import ResponsibilityConfig, generate_queries
from alo_translator.serializers.datalog import DatalogIndexSerializer


def _model(mmd: str):
    return parse_dbt_diagram(mmd)


def _eval_one(mmd: str, formula: str):
    """Serialize+evaluate a single ad-hoc query formula, returning
    (result_dict, generated_program_text)."""
    model = _model(mmd)
    model.queries = [Query(formula_string=formula, query_id="t")]
    serializer = DatalogIndexSerializer(model, evaluation_history="h1", evaluation_moment="m")
    program = serializer._generate_query_rules()
    results = serializer.evaluate()
    return results.get("t"), program


IMPLICATION_HOLDS_MMD = """---
title: q -> Xq holds (q at both m and m1)
---
classDiagram
direction BT
m --> m1 : h1({sd1})
m: q
m1: q
"""

IMPLICATION_FAILS_MMD = """---
title: q -> Xq fails (q at m, ~q at m1)
---
classDiagram
direction BT
m --> m1 : h1({sd1})
m: q
m1: ~q
"""

DISJ_BICOND_MMD = """---
title: disjunction/biconditional test (q and p both true at m)
---
classDiagram
direction BT
m --> m1 : h1({sd1})
m: q, p
"""


def test_implication_no_longer_raises_a_serialization_error():
    _, program = _eval_one(IMPLICATION_HOLDS_MMD, "q -> Xq")
    errors = [l for l in program.splitlines() if l.startswith("# ERROR")]
    assert errors == [], f"expected no serialization errors, got: {errors}"


def test_implication_true_when_antecedent_and_consequent_both_hold():
    result, _ = _eval_one(IMPLICATION_HOLDS_MMD, "q -> Xq")
    assert result["result"] is True


def test_implication_false_when_antecedent_holds_but_consequent_does_not():
    result, _ = _eval_one(IMPLICATION_FAILS_MMD, "q -> Xq")
    assert result["result"] is False


def test_disjunction_true_when_either_disjunct_holds():
    result, program = _eval_one(DISJ_BICOND_MMD, "q v p")
    errors = [l for l in program.splitlines() if l.startswith("# ERROR")]
    assert errors == []
    assert result["result"] is True


def test_disjunction_false_when_both_disjuncts_fail():
    # q and p both true at m -- ~q v ~p should be False.
    result, _ = _eval_one(DISJ_BICOND_MMD, "~q v ~p")
    assert result["result"] is False


def test_disjunction_uses_multiple_rules_sharing_one_helper_head():
    """The fix's actual mechanism: pyDatalog can't OR two rule-body terms
    directly, so disjunction must become >1 rule sharing one fresh head
    (standard Datalog), not a single `|` expression.
    """
    _, program = _eval_one(DISJ_BICOND_MMD, "q v p")
    or_rules = [l for l in program.splitlines() if l.strip().startswith("or_")]
    assert len(or_rules) == 2, f"expected 2 rules sharing an or_N head, got: {or_rules}"
    heads = {l.split("(")[0].strip() for l in or_rules}
    assert len(heads) == 1, f"expected both rules to share one head, got heads: {heads}"


def test_biconditional_true_for_tautology():
    result, program = _eval_one(DISJ_BICOND_MMD, "q <-> q")
    errors = [l for l in program.splitlines() if l.startswith("# ERROR")]
    assert errors == []
    assert result["result"] is True


def test_biconditional_true_when_both_sides_agree():
    # q and p both true at m.
    result, _ = _eval_one(DISJ_BICOND_MMD, "q <-> p")
    assert result["result"] is True


def test_real_baseline_model_unaffected_by_the_fix():
    """Regression guard: the fix must not change output for models that
    never exercise implication/disjunction/biconditional at all -- full
    3.1.mmd responsibility-query pipeline should match the known-good
    Konclude baseline exactly, same as before this fix.
    """
    import json

    mmd_path = Path(__file__).parent.parent / "streamlit_app" / "models" / "3.1.mmd"
    baselines_path = Path(__file__).parent / "fixtures" / "konclude_baselines.json"

    model = parse_dbt_diagram(mmd_path.read_text())
    model.responsibility_config = ResponsibilityConfig(
        target_proposition="q", agents="all", groups="all",
        responsibility_types=["pres", "sres", "res", "dxstit", "but", "ness"],
        history="h1",
    )
    model.queries = generate_queries(model)
    for q in model.queries:
        if q.formula_ast is None:
            q.formula_ast = parse_formula(q.formula_string)

    serializer = DatalogIndexSerializer(model, evaluation_history="h1", evaluation_moment="m")
    results = serializer.evaluate()
    satisfied = {qid for qid, r in results.items() if r.get("result")}

    with open(baselines_path) as f:
        baselines = json.load(f)
    expected = set(baselines["3.1"]["satisfied_queries"])

    assert satisfied == expected


def test_model_background_guard_still_raises_unaffected_by_this_fix():
    """This fix only touches FormulaToDatalog's propositional-connective
    handling for ordinary point-wise model-checking. It has no bearing on
    background theory (open-world/satisfiability semantics) -- the guard
    in DatalogIndexSerializer.__init__ must still raise immediately.
    """
    model = _model(DISJ_BICOND_MMD)
    model.background = ["q -> Xq"]
    with pytest.raises(ValueError, match="background theory"):
        DatalogIndexSerializer(model, evaluation_history="h1", evaluation_moment="m")
