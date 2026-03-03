"""ALOn Serializer - outputs expanded formulas as ALOn strings.

Handles only the "directly translated" constructs that remain after expansion.
"""

from alo_translator.parsers.grammar_transformer import AlonTransformer


class AlonSerializer(AlonTransformer):
    """Serializes expanded ALOn formulas to ALOn string format.

    Converts `=>` expansion axioms to `->`.
    """

    def expansion_axiom(self, items):
        """formula => name  →  formula -> name"""
        pass

    def biconditional(self, items):
        """φ <-> ψ"""
        pass

    def implication(self, items):
        """φ -> ψ"""
        pass

    def disjunction(self, items):
        """φ v ψ"""
        pass

    def conjunction(self, items):
        """φ & ψ"""
        pass

    def negation(self, items):
        """~φ"""
        pass

    def box(self, items):
        """[]φ"""
        pass

    def diamond(self, items):
        """<>φ"""
        pass

    def next(self, items):
        """Xφ"""
        pass

    def do_action(self, items):
        """do(a)"""
        pass

    def free_do_action(self, items):
        """free_do(a)"""
        pass

    def prop(self, items):
        """proposition p"""
        pass

    def top(self, items):
        """T"""
        pass

    def bottom(self, items):
        """_L"""
        pass

    def parens(self, items):
        """(φ)"""
        pass

    # Action and agent expressions
    def individual_action(self, items):
        pass

    def group_action(self, items):
        pass

    def action_mapping(self, items):
        pass

    def action_id(self, items):
        pass

    def individual_agent(self, items):
        pass

    def agent_group(self, items):
        pass

    def named_agent_group(self, items):
        pass
