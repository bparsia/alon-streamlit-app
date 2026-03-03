"""
Formula to OWL visitor for index-based semantics.

This visitor translates ALOn formulas using index-based Kripke semantics
where individuals represent moment/history pairs.

Key translations:
- do(a)    → class a (action class)
- Xφ       → succ some φ
- []φ      → same_moment only φ
- <>φ      → same_moment some φ
- [A pres]φ → same_moment only (do(A) implies (succ some φ))
"""

from xml.etree.ElementTree import Element, SubElement
from typing import Dict, Optional

from ..model.core import ALOModel
from ..model.formula import (
    FormulaNode, Prop, Next, Box, Diamond,
    Conjunction, Disjunction, Negation, Implication, Biconditional,
    DoAction, FreeDoAction, Opposing,
    PotentialResponsibility, StrongResponsibility, PlainResponsibility,
    XSTIT, DXSTIT, ButFor, Ness, ExpectedResult,
    NamedFormula
)


class IndexFormulaToOWLVisitor:
    """
    Visitor for translating ALOn formulas to OWL using index-based semantics.

    Unlike the history-based approach, this uses:
    - same_moment: equivalence relation between indices at same moment
    - succ: successor relation between indices
    - Actions and propositions as classes that indices belong to
    """

    def __init__(
        self,
        base_iri: str,
        model: ALOModel,
        query_id_map: Optional[Dict[str, str]] = None,
        registry=None
    ):
        """
        Initialize the visitor.

        Args:
            base_iri: Base IRI for the ontology
            model: The ALOn model
            query_id_map: Optional mapping from formula strings to query IDs
            registry: Optional FormulaRegistry for resolving NamedFormula references
        """
        self.base_iri = base_iri
        self.model = model
        self.query_id_map = query_id_map or {}
        self.registry = registry

    def _iri(self, name: str) -> str:
        """Generate full IRI for a name."""
        return f"{self.base_iri}{name}"

    def translate(self, formula: FormulaNode) -> Element:
        """Translate a formula to OWL class expression."""
        return self.visit(formula)

    def visit(self, node: FormulaNode) -> Element:
        """Dispatch to appropriate visit method."""
        # Handle NamedFormula by looking up the registered name
        if isinstance(node, NamedFormula):
            if not self.registry:
                raise ValueError("NamedFormula encountered but no registry provided to visitor")
            # formula_key IS the OWL name in the new architecture
            # Return OWL Class reference
            return Element("Class", {"IRI": self._iri(node.formula_key)})

        # Dispatch to appropriate visitor method based on node type
        if isinstance(node, Prop):
            return self._visit_prop(node)
        elif isinstance(node, Negation):
            return self._visit_negation(node)
        elif isinstance(node, Conjunction):
            return self._visit_conjunction(node)
        elif isinstance(node, Disjunction):
            return self._visit_disjunction(node)
        elif isinstance(node, Implication):
            return self._visit_implication(node)
        elif isinstance(node, Biconditional):
            return self._visit_biconditional(node)
        elif isinstance(node, Next):
            return self._visit_next(node)
        elif isinstance(node, Box):
            return self._visit_box(node)
        elif isinstance(node, Diamond):
            return self._visit_diamond(node)
        elif isinstance(node, DoAction):
            return self._visit_do_action(node)
        elif isinstance(node, FreeDoAction):
            return self._visit_free_do_action(node)
        elif isinstance(node, Opposing):
            return self._visit_opposing(node)
        elif isinstance(node, PotentialResponsibility):
            return self._visit_pres(node)
        elif isinstance(node, StrongResponsibility):
            return self._visit_sres(node)
        elif isinstance(node, PlainResponsibility):
            return self._visit_res(node)
        elif isinstance(node, XSTIT):
            return self._visit_xstit(node)
        elif isinstance(node, DXSTIT):
            return self._visit_dxstit(node)
        elif isinstance(node, ButFor):
            return self._visit_but_for(node)
        elif isinstance(node, Ness):
            return self._visit_ness(node)
        else:
            raise NotImplementedError(f"Index visitor doesn't support {type(node).__name__} yet")

    def _visit_prop(self, node: Prop) -> Element:
        """Translate proposition to OWL class."""
        class_elem = Element("Class", {"IRI": self._iri(node.symbol)})
        return class_elem

    def _visit_negation(self, node: Negation) -> Element:
        """Translate negation: ~φ → ObjectComplementOf(φ)"""
        complement = Element("ObjectComplementOf")
        complement.append(self.visit(node.formula))
        return complement

    def _visit_conjunction(self, node: Conjunction) -> Element:
        """Translate conjunction: φ & ψ → ObjectIntersectionOf(φ, ψ)"""
        intersection = Element("ObjectIntersectionOf")
        intersection.append(self.visit(node.left))
        intersection.append(self.visit(node.right))
        return intersection

    def _visit_disjunction(self, node: Disjunction) -> Element:
        """Translate disjunction: φ v ψ → ObjectUnionOf(φ, ψ)"""
        union = Element("ObjectUnionOf")
        union.append(self.visit(node.left))
        union.append(self.visit(node.right))
        return union

    def _visit_implication(self, node: Implication) -> Element:
        """Translate implication: φ -> ψ ≡ ~φ v ψ"""
        union = Element("ObjectUnionOf")
        # Add ~φ
        complement = Element("ObjectComplementOf")
        complement.append(self.visit(node.antecedent))
        union.append(complement)
        # Add ψ
        union.append(self.visit(node.consequent))
        return union

    def _visit_biconditional(self, node: Biconditional) -> Element:
        """Translate biconditional: φ <-> ψ ≡ (φ -> ψ) & (ψ -> φ)"""
        intersection = Element("ObjectIntersectionOf")
        # φ -> ψ
        impl1 = self._visit_implication(Implication(node.left, node.right))
        intersection.append(impl1)
        # ψ -> φ
        impl2 = self._visit_implication(Implication(node.right, node.left))
        intersection.append(impl2)
        return intersection

    def _visit_next(self, node: Next) -> Element:
        """
        Translate temporal next: Xφ → succ some φ

        In index-based semantics, X just looks at the successor via succ.
        """
        restriction = Element("ObjectSomeValuesFrom")
        SubElement(restriction, "ObjectProperty", {"IRI": self._iri("succ")})
        restriction.append(self.visit(node.formula))
        return restriction

    def _visit_box(self, node: Box) -> Element:
        """
        Translate box: []φ → same_moment only φ

        "At all indices at this moment, φ holds"
        """
        restriction = Element("ObjectAllValuesFrom")
        SubElement(restriction, "ObjectProperty", {"IRI": self._iri("same_moment")})
        restriction.append(self.visit(node.formula))
        return restriction

    def _visit_diamond(self, node: Diamond) -> Element:
        """
        Translate diamond: <>φ → same_moment some φ

        "At some index at this moment, φ holds"
        """
        restriction = Element("ObjectSomeValuesFrom")
        SubElement(restriction, "ObjectProperty", {"IRI": self._iri("same_moment")})
        restriction.append(self.visit(node.formula))
        return restriction

    def _visit_do_action(self, node: DoAction) -> Element:
        """
        Translate do(action): do(a) → class a

        In index-based semantics, do(a) is just membership in action class a.
        """
        # Get the action name
        action_name = str(node.action)
        return Element("Class", {"IRI": self._iri(action_name)})

    def _visit_free_do_action(self, node: FreeDoAction) -> Element:
        """
        Translate free_do(action): free_do(a) → do(a) ∧ ¬Opp2a

        In index-based semantics, free_do(a) means the action is done AND
        no opposing action is done (at the same index).
        """
        # Get the action name
        action_name = str(node.action)

        # Build: do(a) ∧ ¬Opp2a
        intersection = Element("ObjectIntersectionOf")

        # do(a)
        SubElement(intersection, "Class", {"IRI": self._iri(action_name)})

        # ¬Opp2a
        complement = SubElement(intersection, "ObjectComplementOf")
        SubElement(complement, "Class", {"IRI": self._iri(f"Opp2{action_name}")})

        return intersection

    def _visit_opposing(self, node: Opposing) -> Element:
        """Translate opposing relation - not yet implemented for index semantics."""
        raise NotImplementedError("Opposing relation not yet implemented for index-based semantics")

    def _visit_pres(self, node: PotentialResponsibility) -> Element:
        """
        Translate potential responsibility: [A pres]φ

        Translation: same_moment only (do(A) implies (succ some φ))

        "At all indices at this moment, if A is done, then successor satisfies φ"
        """
        # Build: do(A) implies (succ some φ)
        # Which is: ~do(A) v (succ some φ)
        implication = Element("ObjectUnionOf")

        # ~do(A)
        not_action = Element("ObjectComplementOf")
        not_action.append(self._action_class(node.agent))
        implication.append(not_action)

        # succ some φ
        succ_phi = Element("ObjectSomeValuesFrom")
        SubElement(succ_phi, "ObjectProperty", {"IRI": self._iri("succ")})
        succ_phi.append(self.visit(node.formula))
        implication.append(succ_phi)

        # Wrap in same_moment only
        restriction = Element("ObjectAllValuesFrom")
        SubElement(restriction, "ObjectProperty", {"IRI": self._iri("same_moment")})
        restriction.append(implication)

        return restriction

    def _visit_sres(self, node: StrongResponsibility) -> Element:
        """
        Translate strong responsibility: [A sres]φ

        Translation: same_moment only (do(A) and (succ some φ))
        """
        # Build: do(A) and (succ some φ)
        conjunction = Element("ObjectIntersectionOf")

        # do(A)
        conjunction.append(self._action_class(node.agent))

        # succ some φ
        succ_phi = Element("ObjectSomeValuesFrom")
        SubElement(succ_phi, "ObjectProperty", {"IRI": self._iri("succ")})
        succ_phi.append(self.visit(node.formula))
        conjunction.append(succ_phi)

        # Wrap in same_moment only
        restriction = Element("ObjectAllValuesFrom")
        SubElement(restriction, "ObjectProperty", {"IRI": self._iri("same_moment")})
        restriction.append(conjunction)

        return restriction

    def _visit_res(self, node: PlainResponsibility) -> Element:
        """
        Translate actual responsibility: [A res]φ

        For now, treat same as sres (they differ in counterfactual semantics).
        """
        return self._visit_sres(StrongResponsibility(node.agent, node.formula))

    def _visit_xstit(self, node: XSTIT) -> Element:
        """Translate XSTIT - not yet implemented for index semantics."""
        raise NotImplementedError("XSTIT not yet implemented for index-based semantics")

    def _visit_dxstit(self, node: DXSTIT) -> Element:
        """Translate DXSTIT - not yet implemented for index semantics."""
        raise NotImplementedError("DXSTIT not yet implemented for index-based semantics")

    def _visit_but_for(self, node: ButFor) -> Element:
        """Translate but-for causation - not yet implemented for index semantics."""
        raise NotImplementedError("But-for not yet implemented for index-based semantics")

    def _visit_ness(self, node: Ness) -> Element:
        """Translate NESS causation - not yet implemented for index semantics."""
        raise NotImplementedError("NESS not yet implemented for index-based semantics")

    def _action_class(self, agent) -> Element:
        """
        Build action class expression for agent/coalition.

        For individual: just the action class
        For coalition: intersection of individual actions
        """
        from ..model.formula import IndividualAgent, AgentGroup, NamedAgentGroup

        if isinstance(agent, IndividualAgent):
            # Single agent - use agent_id as class name
            return Element("Class", {"IRI": self._iri(agent.agent_id)})
        elif isinstance(agent, AgentGroup):
            # Coalition - create intersection of individual agent actions
            # Agent group has sorted list of agent IDs
            intersection = Element("ObjectIntersectionOf")
            for agent_id in sorted(agent.agents):
                # Get the action for this agent from the model
                # For now, just use agent_id as placeholder
                # In practice, we'd need to look up what action this agent does
                SubElement(intersection, "Class", {"IRI": self._iri(agent_id)})
            return intersection
        elif isinstance(agent, NamedAgentGroup):
            # Named group (e.g., "Ag" for all agents)
            return Element("Class", {"IRI": self._iri(agent.name)})
        else:
            # Fallback for string agent (backward compatibility)
            return Element("Class", {"IRI": self._iri(str(agent))})
