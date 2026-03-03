"""Lark Transformer for ALOn grammar.

Base transformer that roundtrips ALOn formulas (parse → serialize back to string).
Each method corresponds to a grammar rule in alon_grammar_clean.lark.
"""

from lark import Transformer


class AlonTransformer(Transformer):
    """Transform parse tree to ALOn string (roundtrip)."""

    # ========== Expansion Axiom ==========

    def expansion_axiom(self, items):
        """formula => name"""
        formula, name = items
        return f"{formula} => {name}"

    # ========== Propositional Logic ==========

    def biconditional(self, items):
        """φ <-> ψ"""
        if len(items) == 1:
            return items[0]
        result = items[-1]
        for item in reversed(items[:-1]):
            result = f"{item} <-> {result}"
        return result

    def implication(self, items):
        """φ -> ψ"""
        if len(items) == 1:
            return items[0]
        result = items[-1]
        for item in reversed(items[:-1]):
            result = f"{item} -> {result}"
        return result

    def disjunction(self, items):
        """φ v ψ"""
        if len(items) == 1:
            return items[0]
        result = items[0]
        for item in items[1:]:
            result = f"{result} v {item}"
        return result

    def conjunction(self, items):
        """φ & ψ"""
        if len(items) == 1:
            return items[0]
        result = items[0]
        for item in items[1:]:
            result = f"{result} & {item}"
        return result

    def negation(self, items):
        """~φ"""
        return f"~{items[0]}"

    # ========== Atoms ==========

    def parens(self, items):
        """(φ)"""
        return f"({items[0]})"

    def top(self, items):
        """T"""
        return "T"

    def bottom(self, items):
        """_L"""
        return "_L"

    def prop(self, items):
        """proposition"""
        return str(items[0])

    # ========== Modal Operators ==========

    def box(self, items):
        """[]φ"""
        return f"[]{items[0]}"

    def diamond(self, items):
        """<>φ"""
        return f"<>{items[0]}"

    def next(self, items):
        """Xφ"""
        # items[0] is X_OP token, items[1] is the formula
        return f"X{items[1]}"

    # ========== PDL-style Modalities ==========

    def pdl_box(self, items):
        """[action]φ"""
        action, formula = items
        return f"[{action}]{formula}"

    def pdl_diamond(self, items):
        """<action>φ"""
        action, formula = items
        return f"<{action}>{formula}"

    # ========== Action Predicates ==========

    def do_action(self, items):
        """do(action)"""
        return f"do({items[0]})"

    def free_do_action(self, items):
        """free_do(action)"""
        return f"free_do({items[0]})"

    def opposing(self, items):
        """action1 |> action2"""
        return f"{items[0]} |> {items[1]}"

    # ========== Causal Operators ==========

    def expected_result(self, items):
        """do(action) [+]-> φ"""
        action, formula = items
        return f"do({action}) [+]-> {formula}"

    def but_for(self, items):
        """but(action, φ)"""
        action, formula = items
        return f"but({action}, {formula})"

    def ness(self, items):
        """ness(action, φ)"""
        action, formula = items
        return f"ness({action}, {formula})"

    # ========== STIT Operators ==========

    def xstit(self, items):
        """[agent XSTIT]φ"""
        agent, formula = items
        return f"[{agent} XSTIT]{formula}"

    def dxstit(self, items):
        """[agent DXSTIT]φ"""
        agent, formula = items
        return f"[{agent} DXSTIT]{formula}"

    # ========== Responsibility Operators ==========

    def pres(self, items):
        """[agent pres]φ"""
        agent, formula = items
        return f"[{agent} pres]{formula}"

    def sres(self, items):
        """[agent sres]φ"""
        agent, formula = items
        return f"[{agent} sres]{formula}"

    def res(self, items):
        """[agent res]φ"""
        agent, formula = items
        return f"[{agent} res]{formula}"

    # ========== Action Expressions ==========

    def individual_action(self, items):
        """action_id"""
        return str(items[0])

    def group_action(self, items):
        """{ mappings }"""
        mappings = ", ".join(items)
        return f"{{{mappings}}}"

    def action_mapping(self, items):
        """num:action"""
        if len(items) == 2:
            return f"{items[0]}:{items[1]}"
        return str(items[0])

    def action_id(self, items):
        """action without agent"""
        return str(items[0])

    # ========== Agent Expressions ==========

    def individual_agent(self, items):
        """agent_num"""
        return str(items[0])

    def agent_group(self, items):
        """{ nums }"""
        nums = ", ".join(str(n) for n in items)
        return f"{{{nums}}}"

    def named_agent_group(self, items):
        """agent_name"""
        return str(items[0])
