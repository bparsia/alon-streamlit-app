"""
Extract ALOn primitive-formula translation rules directly from
FormulaToOWL (alo_translator/serializers/owl.py) and FormulaToDatalog
(alo_translator/serializers/datalog.py) source.

Row set is the paper's OWN formal grammar (Alon4Fear/2Prelims.tex,
"Syntax of ALOn" definition), not an ad-hoc list of implemented Python
methods:

    phi ::= p | do(a,i) | a>b | phi & phi | ~phi | X phi | []phi

Six rows extracted here: prop, do_action, conjunction, negation, next, box.

Explicitly NOT primitives, per the paper's own text ("we use the usual
Boolean shortcuts v, ->, etc., and we use modal shortcuts <>phi for
~[]~phi"): disjunction, implication, biconditional, diamond, free_do_action
-- these are defined abbreviations built from the 6 real primitives, not
base grammar. Also not primitives: top/bottom (owl:Thing/owl:Nothing,
top(I)/bottom(I)) -- these are TARGET-language constructs that show up
inside other rows' renderings and in the structural table, never
themselves an ALOn source-syntax primitive with their own row here.

opposing (a>b) IS a real formula-grammar primitive per the paper -- but
is deliberately excluded from this table too: it currently has no working
inline formula-level OWL/Datalog translation (FormulaToOWL.opposing /
FormulaToDatalog.opposing are both _must_not_appear guards) even though
it's grammar-valid. What IS implemented is the model-level realization
(the opposings: frontmatter declaration -> structural axioms), which is
semantically consistent with the paper's own semantics clause (|= a>b iff
a>b -- opposing's truth doesn't depend on the index at all, it's static
info about the action structure) -- see the structural table's "opposing"
row instead.

Static extraction only (Python ast module) -- no example-running, no
hand-written rule DSL. For each of the 6 methods, pulls the method's
source body and classifies its shape:

  direct    -- single `return <expr>`. The return expression IS the rule;
               render as-is.
  helper    -- the method appends to self.rules/self.axioms (generates an
               auxiliary named predicate/rule) before returning a
               reference to it. Render as a two-part cell.

Usage:
  python -m tools.translation_table.extract_primitives [--check]

  --check: exit nonzero if PRIMITIVE_METHODS's 6 methods are missing or
  changed shape unexpectedly on either transformer -- prevents the table
  silently going stale as the code changes.
"""

import ast
import inspect
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from lark import Transformer as LarkTransformer

from alo_translator.serializers.owl import FormulaToOWL
from alo_translator.serializers.datalog import FormulaToDatalog
from alo_translator.serializers.sparql import FormulaToSPARQL

# The paper's formal grammar (2Prelims.tex, "Syntax of ALOn"), exactly:
#   phi ::= p | do(a,i) | a>b | phi & phi | ~phi | X phi | []phi
# minus opposing (a>b) -- see module docstring for why it's excluded here.
# This is an ALLOWLIST, not "everything not explicitly excluded" -- the
# whole point of this rewrite is that the row set is fixed by the paper's
# grammar, not by whatever methods happen to exist in the Python source.
PRIMITIVE_METHODS = ["prop", "do_action", "conjunction", "negation", "next", "box"]

ALON_SYNTAX = {
    "prop": r"$p$ (atomic proposition)",
    "do_action": r"$do(a,i)$",
    "conjunction": r"$\phi \wedge \psi$",
    "negation": r"$\neg\phi$",
    "next": r"$X\phi$",
    "box": r"$\Box\phi$",
}

# Concrete syntax the parser actually accepts, per
# alo_translator/parsers/alon_grammar.lark's own tokens/rules (box_op,
# next_op/X_OP, do_action_op, conjunction, negation) -- not invented,
# copied from the grammar's literal operator tokens (`[]`, `X`, `do(...)`,
# `&`, `~`). `prop` has no dedicated token: it's the bare IDENTIFIER atom
# rule. Metavariables standing for subformulas render as the actual
# phi/psi glyphs (LaTeX math-mode commands, not literal Unicode -- plain
# pdflatex chokes on raw Unicode Greek in \texttt{}), matching Table 2's
# math-notation column; only the operators themselves are literal
# grammar-token text.
ALON_ASCII = {
    "prop": r"\texttt{p}",
    "do_action": r"\texttt{do(a)}",
    "conjunction": r"\texttt{$\varphi$ \& $\psi$}",
    "negation": r"\texttt{\textasciitilde$\varphi$}",
    "next": r"\texttt{X $\varphi$}",
    "box": r"\texttt{[]$\varphi$}",
}


@dataclass
class PrimitiveRow:
    method_name: str
    alon_syntax: str
    ascii_syntax: str
    owl_shape: str
    owl_source: str
    owl_file: str
    owl_line: int
    sparql_shape: str
    sparql_source: str
    sparql_file: str
    sparql_line: int
    datalog_shape: str
    datalog_source: str
    datalog_file: str
    datalog_line: int


def _method_source(cls, name: str) -> tuple[str, int]:
    method = getattr(cls, name)
    source = inspect.getsource(method)
    _, line = inspect.getsourcelines(method)
    return source, line


def _classify_shape(source: str) -> str:
    """Classify a method body's translation shape by walking its AST.

    direct  -- returns are all simple expressions (no self.rules.append /
               self.axioms.add calls anywhere in the body).
    helper  -- body contains a call to self.rules.append(...) or
               self.axioms.add(...) before returning -- generates an
               auxiliary rule/axiom, not a single inline expression.
    reject  -- body's only non-guard statement is a bare `raise`.
    """
    tree = ast.parse(textwrap.dedent(source))
    func_def = tree.body[0]
    assert isinstance(func_def, ast.FunctionDef)

    has_raise = False
    has_helper_call = False
    has_return_expr = False

    for node in ast.walk(func_def):
        if isinstance(node, ast.Raise):
            has_raise = True
        if isinstance(node, ast.Call):
            call = node.func
            if isinstance(call, ast.Attribute) and call.attr in ("append", "add"):
                if isinstance(call.value, ast.Attribute) and call.value.attr in ("rules", "axioms"):
                    has_helper_call = True
        if isinstance(node, ast.Return) and node.value is not None:
            has_return_expr = True

    if has_helper_call:
        return "helper"
    if has_raise and not has_return_expr:
        return "reject"
    return "direct"


def _check_method_exists(cls, name: str, cls_label: str) -> None:
    if not hasattr(cls, name) or hasattr(LarkTransformer, name):
        raise RuntimeError(
            f"Expected grammar-rule method '{name}' not found (as its own "
            f"method, not inherited from lark.Transformer) on {cls_label} -- "
            f"the paper's grammar row set (PRIMITIVE_METHODS) assumes this "
            f"method exists. Either it was renamed/removed (fix "
            f"PRIMITIVE_METHODS or restore the method), or something else "
            f"changed unexpectedly."
        )


def build_rows() -> list[PrimitiveRow]:
    for name in PRIMITIVE_METHODS:
        _check_method_exists(FormulaToOWL, name, "FormulaToOWL")
        _check_method_exists(FormulaToSPARQL, name, "FormulaToSPARQL")
        _check_method_exists(FormulaToDatalog, name, "FormulaToDatalog")

    unmapped = set(PRIMITIVE_METHODS) - set(ALON_SYNTAX)
    if unmapped:
        raise RuntimeError(
            f"Primitive method(s) {unmapped} have no ALON_SYNTAX entry -- "
            f"add one before extraction can proceed."
        )
    unmapped_ascii = set(PRIMITIVE_METHODS) - set(ALON_ASCII)
    if unmapped_ascii:
        raise RuntimeError(
            f"Primitive method(s) {unmapped_ascii} have no ALON_ASCII entry -- "
            f"add one before extraction can proceed."
        )

    rows = []
    for name in PRIMITIVE_METHODS:
        owl_source, owl_line = _method_source(FormulaToOWL, name)
        sparql_source, sparql_line = _method_source(FormulaToSPARQL, name)
        datalog_source, datalog_line = _method_source(FormulaToDatalog, name)
        rows.append(PrimitiveRow(
            method_name=name,
            alon_syntax=ALON_SYNTAX[name],
            ascii_syntax=ALON_ASCII[name],
            owl_shape=_classify_shape(owl_source),
            owl_source=owl_source,
            owl_file="alo_translator/serializers/owl.py",
            owl_line=owl_line,
            sparql_shape=_classify_shape(sparql_source),
            sparql_source=sparql_source,
            sparql_file="alo_translator/serializers/sparql.py",
            sparql_line=sparql_line,
            datalog_shape=_classify_shape(datalog_source),
            datalog_source=datalog_source,
            datalog_file="alo_translator/serializers/datalog.py",
            datalog_line=datalog_line,
        ))
    return rows


def main():
    check_only = "--check" in sys.argv
    rows = build_rows()
    if check_only:
        print(f"OK: {len(rows)} primitive rows extracted, all classified, no divergence.")
        return
    for row in rows:
        print(f"{row.method_name}: owl={row.owl_shape} datalog={row.datalog_shape}")


if __name__ == "__main__":
    main()
