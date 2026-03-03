"""
Formula Registry for tracking unique formulas and assigning stable names.

This module implements the simplified registry architecture where:
- formulas: Dict[str, FormulaNode] maps OWL_name -> processed_expansion_tree
- labels: Dict[str, str] maps OWL_name -> human-readable label
- pending: List[FormulaNode] is a FIFO queue of formulas to process
"""

from typing import Dict, List, Optional
from alo_translator.model.formula import FormulaNode


class FormulaRegistry:
    """
    Tracks unique formulas and their processed expansion trees.

    The registry uses OWL class names as keys (from formula.to_owl_name()).
    Each formula is processed to replace nameable subformulas with NamedFormula references.
    The resulting expansion tree is stored in the formulas dictionary.
    """

    def __init__(self):
        self.formulas: Dict[str, FormulaNode] = {}  # OWL_name -> processed_expansion_tree
        self.labels: Dict[str, str] = {}            # OWL_name -> human-readable label
        self.pending: List[FormulaNode] = []        # FIFO queue of formulas to process

    def register(self, formula: FormulaNode, label: Optional[str] = None) -> str:
        """
        Add a formula to the pending queue for processing.

        This does NOT store the formula in the registry yet - that happens
        during expansion when the formula is popped from the pending queue
        and its expansion tree is processed.

        Args:
            formula: The formula to register
            label: Optional human-readable label (e.g., "do(sd1) [+]-> q") for rdfs:label

        Returns:
            OWL class name for this formula (from formula.to_owl_name())
        """
        name = formula.to_owl_name()

        # Check if already processed (deduplication)
        if name in self.formulas:
            return name

        # Check if already in pending queue (avoid duplicates)
        for pending_formula in self.pending:
            if pending_formula.to_owl_name() == name:
                return name

        # Add to pending queue
        self.pending.append(formula)

        # Store label if provided
        if label:
            self.labels[name] = label

        return name

    def store(self, name: str, processed_expansion: FormulaNode):
        """
        Store a processed expansion tree in the registry.

        This is called by the HierarchicalExpander after it has:
        1. Expanded the formula
        2. Replaced nameable subformulas with NamedFormula references

        Args:
            name: OWL class name for this formula
            processed_expansion: The expansion tree with NamedFormula references inserted
        """
        self.formulas[name] = processed_expansion

    def get_formula(self, name: str) -> Optional[FormulaNode]:
        """Get the processed expansion tree for a formula by its OWL name."""
        return self.formulas.get(name)

    def get_label(self, name: str) -> Optional[str]:
        """Get the human-readable label for a formula by its OWL name."""
        return self.labels.get(name)

    def is_registered(self, name: str) -> bool:
        """Check if a formula with this OWL name is already registered."""
        return name in self.formulas

    def has_pending(self) -> bool:
        """Check if there are formulas waiting to be processed."""
        return len(self.pending) > 0

    def pop_pending(self) -> Optional[FormulaNode]:
        """
        Pop the next formula from the pending queue (FIFO).

        Returns:
            The next formula to process, or None if queue is empty
        """
        if self.pending:
            return self.pending.pop(0)  # FIFO: pop from front
        return None

    def __len__(self) -> int:
        """Return the number of registered formulas."""
        return len(self.formulas)

    def __repr__(self) -> str:
        return f"FormulaRegistry({len(self)} formulas, {len(self.pending)} pending)"
