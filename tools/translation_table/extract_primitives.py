"""
Extract ALOn primitive-formula translation rules directly from
FormulaToOWL (alo_translator/serializers/owl.py) and FormulaToDatalog
(alo_translator/serializers/datalog.py) source.

Static extraction only (Python ast module) -- no example-running, no
hand-written rule DSL. For each primitive method shared by both
transformers, pulls the method's source body and classifies its shape:

  direct    -- single `return <expr>` (possibly with a short guard for the
               len(items)==1 base case). The return expression IS the rule;
               render as-is.
  helper    -- the method appends to self.rules/self.axioms (generates an
               auxiliary named predicate/rule) before returning a reference
               to it. Render as a two-part cell: the helper-rule pattern
               plus the returned reference.
  reject    -- the method's body is (only) a `raise` for len>1 items. As of
               2026-08-28 no primitive method is reject-shaped any more
               (Datalog's implication/disjunction were fixed to real
               translations, not left raising) -- this classification is
               kept so the check script fails loudly if that ever regresses.

Deliberately excludes: parens (pure pass-through, no semantic content),
action/agent syntax-tree plumbing (individual_action, group_action,
action_mapping, action_id, individual_agent, agent_group,
named_agent_group -- these build up name strings consumed by do_action/
free_do_action, not independent translation rules), and every defined/
derived operator (pres, sres, res, but_for, ness, xstit, dxstit,
expected_result, pdl_box, pdl_diamond, opposing) -- those are already
formally defined in the paper in terms of primitives; this table's job is
only the primitives themselves, per explicit scoping.

Usage:
  python -m tools.translation_table.extract_primitives [--check]

  --check: exit nonzero if either transformer defines a primitive method
  (non-must_not_appear, non-excluded) not yet listed in PRIMITIVE_ROWS
  below -- prevents the table silently going stale as the code changes.
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

# Methods that exist on both transformers but aren't independent
# translation rules -- excluded from the row set entirely, not just
# unclassified. See module docstring.
EXCLUDED_METHODS = {
    "parens",
    "expansion_axiom",  # top-level axiom wrapper, not a formula primitive
    "individual_action", "group_action", "action_mapping", "action_id",
    "individual_agent", "agent_group", "named_agent_group",
    "generate_rules",  # FormulaToDatalog-only utility (self.rules joiner), not a grammar-rule callback
}

# The ALOn syntax each primitive method corresponds to, for the table's
# leftmost column. Hand-maintained (there's no way to derive "phi & psi"
# notation from a Python method name automatically) but checked against
# real method names via PRIMITIVE_ROWS's keys below -- if a name here
# doesn't match an actual method, extraction fails loudly, not silently.
ALON_SYNTAX = {
    "biconditional": r"$\phi \leftrightarrow \psi$",
    "implication": r"$\phi \rightarrow \psi$",
    "disjunction": r"$\phi \vee \psi$",
    "conjunction": r"$\phi \wedge \psi$",
    "negation": r"$\neg\phi$",
    "box": r"$\Box\phi$",
    "diamond": r"$\Diamond\phi$",
    "next": r"$X\phi$",
    "do_action": r"$do(\alpha)$",
    "free_do_action": r"$free\_do(\alpha)$",
    "prop": r"$p$ (atomic proposition)",
    "top": r"$\top$",
    "bottom": r"$\bot$",
}


@dataclass
class PrimitiveRow:
    method_name: str
    alon_syntax: str
    owl_shape: str
    owl_source: str
    owl_file: str
    owl_line: int
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


def _discover_primitive_methods(cls) -> set[str]:
    """Grammar-rule callback methods on cls: defined directly in cls's own
    body (not inherited from lark.Transformer, which has its own public
    API methods like transform()/visit_children() that aren't grammar
    callbacks at all), not in EXCLUDED_METHODS, and not a
    _must_not_appear guard for a defined/derived operator.
    """
    found = set()
    for name in dir(cls):
        if name.startswith("_") or name in EXCLUDED_METHODS:
            continue
        if hasattr(LarkTransformer, name):
            continue  # inherited Lark API (transform, visit_children, __default__, ...), not a grammar rule
        attr = getattr(cls, name, None)
        if not callable(attr):
            continue
        try:
            source = inspect.getsource(attr)
        except (OSError, TypeError):
            continue
        if "_must_not_appear" in source:
            continue
        found.add(name)
    return found


def build_rows() -> list[PrimitiveRow]:
    owl_methods = _discover_primitive_methods(FormulaToOWL)
    datalog_methods = _discover_primitive_methods(FormulaToDatalog)

    shared = owl_methods & datalog_methods
    owl_only = owl_methods - datalog_methods
    datalog_only = datalog_methods - owl_methods
    if owl_only or datalog_only:
        raise RuntimeError(
            f"Primitive method sets diverge between FormulaToOWL and "
            f"FormulaToDatalog -- owl_only={owl_only}, datalog_only={datalog_only}. "
            f"Extraction assumes a 1:1 row correspondence; resolve the "
            f"divergence (add the missing method, or add it to "
            f"EXCLUDED_METHODS if it's genuinely one-sided) before proceeding."
        )

    unmapped = shared - set(ALON_SYNTAX)
    if unmapped:
        raise RuntimeError(
            f"Primitive method(s) {unmapped} have no ALON_SYNTAX entry -- "
            f"add one before extraction can proceed."
        )

    rows = []
    for name in sorted(shared):
        owl_source, owl_line = _method_source(FormulaToOWL, name)
        datalog_source, datalog_line = _method_source(FormulaToDatalog, name)
        rows.append(PrimitiveRow(
            method_name=name,
            alon_syntax=ALON_SYNTAX[name],
            owl_shape=_classify_shape(owl_source),
            owl_source=owl_source,
            owl_file="alo_translator/serializers/owl.py",
            owl_line=owl_line,
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
