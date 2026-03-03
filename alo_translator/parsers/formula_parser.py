"""
Compositional parser for ALOn formulae using Lark.

This module provides parsing for the full ALOn language, producing
FormulaNode IR (alo_translator.model.formula) as output.

Examples:
    >>> from alo_translator.parsers.formula_parser import parse_formula
    >>> ast = parse_formula("Xq")
    >>> print(ast)  # Next(Prop("q"))

    >>> ast = parse_formula("p & Xq")
    >>> print(ast)  # Conjunction(Prop("p"), Next(Prop("q")))
"""

from pathlib import Path
from typing import List
from lark import Lark, Transformer
from alo_translator.model.formula import (
    # Formula nodes
    FormulaNode, Prop, DoAction, FreeDoAction, Opposing,
    Negation, Conjunction, Disjunction, Implication, Biconditional,
    Box, Diamond, Next, Top, Bottom,
    PDLBox, PDLDiamond, ExpectedResult, ButFor, Ness,
    XSTIT, DXSTIT, PotentialResponsibility, StrongResponsibility, PlainResponsibility,
    # Action/Agent types
    IndividualAction, GroupAction, IndividualAgent, AgentGroup, NamedAgentGroup,
)


class FormulaTransformer(Transformer):
    """Transform Lark parse tree into FormulaNode IR."""

    # ========================================================================
    # Propositional operators
    # ========================================================================

    def prop(self, items):
        """Propositional atom: q"""
        return Prop(str(items[0]))

    def top(self, items):
        """Top (tautology): T"""
        return Top()

    def bottom(self, items):
        """Bottom (contradiction): _L"""
        return Bottom()

    def negation(self, items):
        """Negation: ~φ"""
        return Negation(items[0])

    def conjunction_op(self, items):
        """Conjunction: φ & ψ [& χ ...]"""
        if len(items) == 1:
            return items[0]
        # Left-associate: (((a & b) & c) & d)
        result = items[0]
        for item in items[1:]:
            result = Conjunction(result, item)
        return result

    def disjunction_op(self, items):
        """Disjunction: φ v ψ [v χ ...]"""
        if len(items) == 1:
            return items[0]
        # Left-associate
        result = items[0]
        for item in items[1:]:
            result = Disjunction(result, item)
        return result

    def implication_op(self, items):
        """Implication: φ -> ψ [-> χ ...]"""
        if len(items) == 1:
            return items[0]
        # Right-associate: (a -> (b -> c))
        result = items[-1]
        for item in reversed(items[:-1]):
            result = Implication(item, result)
        return result

    def biconditional_op(self, items):
        """Biconditional: φ <-> ψ [<-> χ ...]"""
        if len(items) == 1:
            return items[0]
        # Left-associate
        result = items[0]
        for item in items[1:]:
            result = Biconditional(result, item)
        return result

    def parens(self, items):
        """Parenthesized formula: (φ)"""
        return items[0]

    # ========================================================================
    # Primitive modal operators
    # ========================================================================

    def box(self, items):
        """Box (historical necessity): []φ"""
        return Box(items[0])

    def diamond(self, items):
        """Diamond (historical possibility): <>φ"""
        return Diamond(items[0])

    def next(self, items):
        """Next (temporal): Xφ"""
        # items[0] is X_OP token, items[1] is the formula
        return Next(items[1] if len(items) > 1 else items[0])

    # ========================================================================
    # Action expressions
    # ========================================================================

    def individual_action(self, items):
        """Individual action: sd1"""
        # Parse action_type and agent from identifier like "sd1"
        action_id = str(items[0])
        # Split into action_type and agent
        # Assume last digit(s) are agent, rest is action_type
        import re
        match = re.match(r'([a-zA-Z_]+)([0-9]+)', action_id)
        if match:
            action_type, agent = match.groups()
            return IndividualAction(action_type, agent)
        else:
            # If no number, treat whole thing as action_type with empty agent
            # This shouldn't happen in valid input, but handle gracefully
            raise ValueError(f"Invalid action format: {action_id} (expected format like 'sd1')")

    def group_action(self, items):
        """Group action: {1:sd, 2:ss} or {sd1, ss2}"""
        # items is a list of action mappings
        actions = {}
        for mapping in items:
            if isinstance(mapping, tuple):
                # (agent, action_type) from action_mapping
                agent, action_type = mapping
                actions[agent] = action_type
            elif isinstance(mapping, IndividualAction):
                # From action_id - already parsed individual action
                actions[mapping.agent] = mapping.action_type
        return GroupAction(actions)

    def action_mapping(self, items):
        """Action mapping in group: agent:action_type"""
        agent = str(items[0])
        action_type = str(items[1])
        return (agent, action_type)

    def action_id(self, items):
        """Action identifier (fallback for group actions): sd1"""
        return self.individual_action(items)

    # ========================================================================
    # Agent expressions
    # ========================================================================

    def individual_agent(self, items):
        """Individual agent: 1"""
        return IndividualAgent(str(items[0]))

    def agent_group(self, items):
        """Agent group: {1, 2, 3}"""
        agents = [str(item) for item in items]
        return AgentGroup(agents)

    def named_agent_group(self, items):
        """Named agent group: Ag"""
        return NamedAgentGroup(str(items[0]))

    # ========================================================================
    # Action predicates
    # ========================================================================

    def do_action(self, items):
        """Do action: do(a1) or do({1:sd, 2:ss})"""
        return DoAction(items[0])

    def free_do_action(self, items):
        """Free do action: free_do(a1)"""
        return FreeDoAction(items[0])

    def opposing(self, items):
        """Opposing relation: a1 |> a2"""
        return Opposing(items[0], items[1])

    # ========================================================================
    # PDL-style modalities
    # ========================================================================

    def pdl_box(self, items):
        """PDL box: [a1]φ"""
        return PDLBox(items[0], items[1])

    def pdl_diamond(self, items):
        """PDL diamond: <a1>φ"""
        return PDLDiamond(items[0], items[1])

    # ========================================================================
    # Causal operators
    # ========================================================================

    def expected_result(self, items):
        """Expected result: do(a1) [+]-> φ"""
        return ExpectedResult(items[0], items[1])

    def but_for(self, items):
        """But-for causation: but(a1, φ)"""
        return ButFor(items[0], items[1])

    def ness(self, items):
        """NESS causation: ness(a1, φ)"""
        return Ness(items[0], items[1])

    # ========================================================================
    # STIT operators
    # ========================================================================

    def xstit(self, items):
        """XSTIT: [1 xstit]φ"""
        return XSTIT(items[0], items[1])

    def dxstit(self, items):
        """Deliberative XSTIT: [1 dxstit]φ"""
        return DXSTIT(items[0], items[1])

    # ========================================================================
    # Responsibility operators
    # ========================================================================

    def pres(self, items):
        """Potential responsibility: [1 pres]φ"""
        return PotentialResponsibility(items[0], items[1])

    def sres(self, items):
        """Strong responsibility: [1 sres]φ"""
        return StrongResponsibility(items[0], items[1])

    def res(self, items):
        """Plain responsibility: [1 res]φ"""
        return PlainResponsibility(items[0], items[1])


# Load grammar file
_grammar_path = Path(__file__).parent / "alon_grammar.lark"
with open(_grammar_path) as f:
    _grammar = f.read()

# Create parser with transformer
_parser = Lark(_grammar, parser='lalr', transformer=FormulaTransformer())

# Create parser without transformer (for debugging)
_parser_debug = Lark(_grammar, parser='lalr')


def parse_formula(formula_string: str) -> FormulaNode:
    """
    Parse an ALOn formula string into FormulaNode IR.

    Args:
        formula_string: The formula as a string (e.g., "Xq", "p & Xq")

    Returns:
        A FormulaNode representing the parsed formula

    Raises:
        lark.exceptions.LarkError: If the formula is malformed

    Examples:
        >>> parse_formula("q")
        Prop(symbol='q')

        >>> parse_formula("Xq")
        Next(formula=Prop(symbol='q'))

        >>> parse_formula("p & Xq")
        Conjunction(left=Prop(symbol='p'), right=Next(formula=Prop(symbol='q')))

        >>> parse_formula("[sd1]q")
        PDLBox(action=IndividualAction(action_type='sd', agent='1'), formula=Prop(symbol='q'))

        >>> parse_formula("[1 pres]q")
        PotentialResponsibility(agent=IndividualAgent(agent_id='1'), formula=Prop(symbol='q'))
    """
    return _parser.parse(formula_string)


def parse_formula_debug(formula_string: str):
    """
    Parse a formula and return the raw parse tree (for debugging).

    Args:
        formula_string: The formula as a string

    Returns:
        The Lark parse tree before transformation
    """
    return _parser_debug.parse(formula_string)
