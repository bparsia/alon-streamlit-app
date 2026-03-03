"""
Hierarchical Formula Expander for ALOn formulas.

This module implements the simplified hierarchical expansion architecture where:
1. Formulas are popped from the pending queue (FIFO)
2. Each formula is expanded (if needs_expansion)
3. Subformulas are recursively processed to insert NamedFormula references
4. The processed expansion tree is stored in the registry
"""

from typing import Optional
from alo_translator.model.formula import (
    FormulaNode, NamedFormula,
    Negation, Conjunction, Disjunction, Implication, Biconditional,
    Next, Box, Diamond, FreeDoAction,
    ExpectedResult, ButFor, Ness,
    PotentialResponsibility, StrongResponsibility, PlainResponsibility,
    XSTIT, DXSTIT, PDLBox, PDLDiamond,
    Prop, DoAction
)
from alo_translator.model.core import ALOModel
from alo_translator.parsers.formula_registry import FormulaRegistry


class HierarchicalExpander:
    """
    Expands formulas breadth-first using the registry pattern.

    The expander:
    1. Pops formulas from the pending queue (FIFO)
    2. Expands each formula (if it needs expansion)
    3. Recursively processes the expansion tree to replace nameable subformulas with NamedFormula references
    4. Stores the processed expansion tree in the registry
    """

    def __init__(self, model: ALOModel, registry: FormulaRegistry,
                 evaluation_history: str = "h1"):
        """
        Initialize the hierarchical expander.

        Args:
            model: The ALOModel containing agents, actions, and histories
            registry: The FormulaRegistry for tracking unique formulas
            evaluation_history: Name of the history to evaluate formulas in (default: "h1")
        """
        self.model = model
        self.registry = registry
        self.evaluation_history = evaluation_history

    def expand_all(self):
        """
        Expand all formulas in the pending queue breadth-first.

        For each formula:
        1. Pop from pending queue
        2. Expand if needed (or use formula itself for primitives)
        3. Recursively process the expansion tree to insert NamedFormula references
        4. Store in registry
        """
        while self.registry.has_pending():
            # Pop next formula from queue (FIFO)
            formula = self.registry.pop_pending()
            if formula is None:
                break

            # Get the OWL name for this formula
            name = formula.to_owl_name()

            # Skip if already processed (deduplication)
            if self.registry.is_registered(name):
                continue

            # Get the expansion
            if formula.needs_expansion():
                # Call formula's expand() method
                expanded = formula.expand(self)
            else:
                # Primitives/modal operators expand to themselves
                expanded = formula

            # Recursively process the expansion tree to insert NamedFormula references
            # But process the children, not the root node itself (which is already being registered)
            processed = self._process_formula_children(expanded)

            # Store in registry
            self.registry.store(name, processed)

    def _process_formula_children(self, node: FormulaNode) -> FormulaNode:
        """
        Process the children of a formula node without replacing the node itself.

        This is used for the top-level formula being registered - we want to process
        its children but not replace the formula itself with a NamedFormula reference.

        Args:
            node: The formula node whose children should be processed

        Returns:
            New formula node with processed children
        """
        # Basic primitives: no children to process
        if isinstance(node, (Prop, DoAction, NamedFormula)):
            return node

        # Structural connectives: recurse into children
        if isinstance(node, Negation):
            return Negation(self._process_subformulas(node.formula))

        if isinstance(node, Conjunction):
            return Conjunction(
                self._process_subformulas(node.left),
                self._process_subformulas(node.right)
            )

        if isinstance(node, Disjunction):
            return Disjunction(
                self._process_subformulas(node.left),
                self._process_subformulas(node.right)
            )

        if isinstance(node, Implication):
            return Implication(
                self._process_subformulas(node.antecedent),
                self._process_subformulas(node.consequent)
            )

        if isinstance(node, Biconditional):
            return Biconditional(
                self._process_subformulas(node.left),
                self._process_subformulas(node.right)
            )

        # Modal operators: process child
        if isinstance(node, Next):
            return Next(self._process_subformulas(node.formula))

        if isinstance(node, Box):
            return Box(self._process_subformulas(node.formula))

        if isinstance(node, Diamond):
            return Diamond(self._process_subformulas(node.formula))

        # Unhandled node type - return as-is
        return node

    def _process_subformulas(self, node: FormulaNode) -> FormulaNode:
        """
        Recursively walk formula tree, replacing nameable subformulas with NamedFormula references.

        Rules:
        - If node.should_be_named(): Replace with NamedFormula, add to pending queue
        - If structural connective: Keep as-is, but recurse into children
        - If basic primitive (Prop, DoAction): Keep as-is (will become inline class ref)

        Args:
            node: The formula node to process

        Returns:
            Processed formula node with NamedFormula references inserted
        """
        # Basic primitives: keep as-is (will be translated inline)
        if isinstance(node, (Prop, DoAction)):
            return node

        # Check if this subformula should be named
        if node.should_be_named():
            # Register this formula (adds to pending queue if not already there)
            name = self.registry.register(node)
            # Return a NamedFormula reference instead
            # formula_key is the OWL name
            return NamedFormula(formula_key=name)

        # Structural connectives: recurse into children
        if isinstance(node, Negation):
            return Negation(self._process_subformulas(node.formula))

        if isinstance(node, Conjunction):
            return Conjunction(
                self._process_subformulas(node.left),
                self._process_subformulas(node.right)
            )

        if isinstance(node, Disjunction):
            return Disjunction(
                self._process_subformulas(node.left),
                self._process_subformulas(node.right)
            )

        if isinstance(node, Implication):
            return Implication(
                self._process_subformulas(node.antecedent),
                self._process_subformulas(node.consequent)
            )

        if isinstance(node, Biconditional):
            return Biconditional(
                self._process_subformulas(node.left),
                self._process_subformulas(node.right)
            )

        # Modal operators Box and Diamond: recurse into child (they're structural)
        if isinstance(node, Box):
            return Box(self._process_subformulas(node.formula))

        if isinstance(node, Diamond):
            return Diamond(self._process_subformulas(node.formula))

        # NamedFormula: already a reference, keep as-is
        if isinstance(node, NamedFormula):
            return node

        # If we got here, it's an unhandled node type - keep as-is
        # This includes nodes that are already properly processed
        return node

    def __repr__(self) -> str:
        return (f"HierarchicalExpander("
                f"registry={self.registry})")
