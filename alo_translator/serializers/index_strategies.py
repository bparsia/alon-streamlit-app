"""
Strategy pattern for same_moment representation in index-based OWL serialization.

This module provides different strategies for representing same-moment relationships
and closing the world under the open-world assumption.
"""

from abc import ABC, abstractmethod
from typing import Dict, List
from xml.etree.ElementTree import Element, SubElement

from .index_formula_visitor import IndexFormulaToOWLVisitor
from .index_formula_visitor_reified import IndexFormulaToOWLVisitorReified


class SameMomentStrategy(ABC):
    """Abstract base for same_moment representation strategies."""

    @abstractmethod
    def add_declarations(self, ontology: Element, serializer) -> None:
        """
        Add any strategy-specific declarations (e.g., moment individuals).

        Args:
            ontology: The OWL ontology element
            serializer: The OWLIndexSerializer instance (for accessing helper methods)
        """
        pass

    @abstractmethod
    def add_structural_axioms(self, ontology: Element, serializer) -> None:
        """
        Add property declarations and characteristics.

        Args:
            ontology: The OWL ontology element
            serializer: The OWLIndexSerializer instance
        """
        pass

    @abstractmethod
    def add_same_moment_structure(self, ontology: Element, serializer) -> None:
        """
        Add same-moment assertions and world closure.

        Args:
            ontology: The OWL ontology element
            serializer: The OWLIndexSerializer instance
        """
        pass

    @abstractmethod
    def get_formula_visitor(self, base_iri: str, model, query_id_map: Dict[str, str], registry=None):
        """
        Return appropriate formula visitor for this strategy.

        Args:
            base_iri: Base IRI for the ontology
            model: The ALOn model
            query_id_map: Mapping from formula strings to query IDs
            registry: Optional FormulaRegistry for resolving NamedFormula references
            

        Returns:
            IndexFormulaToOWLVisitor or subclass appropriate for this strategy
        """
        pass


class EquivChainedNominalStrategy(SameMomentStrategy):
    """
    Strategy 1: Equivalence relation with chained assertions and nominal closure.

    - Property: same_moment (reflexive, symmetric, transitive)
    - Assertions: Chained (minimal) - m_h1 same_moment m_h2, m_h2 same_moment m_h3, etc.
    - World closure: Nominal class constraint on one index per moment
    - Formula translation: []φ → same_moment only φ

    Status: Semantically correct (verified in Protégé), but Konclude has issues
    """

    def add_declarations(self, ontology: Element, serializer) -> None:
        """No extra declarations needed for equivalence relation approach."""
        pass

    def add_structural_axioms(self, ontology: Element, serializer) -> None:
        """Add same_moment property with equivalence relation characteristics."""
        # Declare same_moment property
        serializer._declare_object_property(ontology, "same_moment")

        # same_moment is an equivalence relation
        # Add reflexive, symmetric, transitive characteristics
        reflexive = SubElement(ontology, "ReflexiveObjectProperty")
        SubElement(reflexive, "ObjectProperty", {"IRI": serializer._iri("same_moment")})

        symmetric = SubElement(ontology, "SymmetricObjectProperty")
        SubElement(symmetric, "ObjectProperty", {"IRI": serializer._iri("same_moment")})

        transitive = SubElement(ontology, "TransitiveObjectProperty")
        SubElement(transitive, "ObjectProperty", {"IRI": serializer._iri("same_moment")})

    def add_same_moment_structure(self, ontology: Element, serializer) -> None:
        """
        Add chained same_moment assertions and nominal class constraint.

        Chains indices together and adds nominal class constraint to close
        the equivalence class (for proper universal quantification with ObjectAllValuesFrom).
        """
        # Group indices by moment
        indices_by_moment: Dict[str, List[str]] = {}
        for moment, history in serializer._get_all_indices():
            if moment not in indices_by_moment:
                indices_by_moment[moment] = []
            indices_by_moment[moment].append(serializer._index_name(moment, history))

        # For each moment, chain indices and add closure constraint
        for moment, indices in indices_by_moment.items():
            # Chain indices together with same_moment (for transitivity)
            for i in range(len(indices) - 1):
                assertion = SubElement(ontology, "ObjectPropertyAssertion")
                SubElement(assertion, "ObjectProperty", {"IRI": serializer._iri("same_moment")})
                SubElement(assertion, "NamedIndividual", {"IRI": serializer._iri(indices[i])})
                SubElement(assertion, "NamedIndividual", {"IRI": serializer._iri(indices[i + 1])})

            # Add nominal class constraint to close the equivalence class
            # For at least one index (use first), assert: same_moment only {all indices at this moment}
            if indices:
                closure_axiom = SubElement(ontology, "ClassAssertion")
                # Build: same_moment only {i1, i2, i3, ...}
                restriction = SubElement(closure_axiom, "ObjectAllValuesFrom")
                SubElement(restriction, "ObjectProperty", {"IRI": serializer._iri("same_moment")})

                # Create nominal class (enumeration of individuals)
                nominal = SubElement(restriction, "ObjectOneOf")
                for index in indices:
                    SubElement(nominal, "NamedIndividual", {"IRI": serializer._iri(index)})

                # Apply to first index in the equivalence class
                SubElement(closure_axiom, "NamedIndividual", {"IRI": serializer._iri(indices[0])})

    def get_formula_visitor(self, base_iri: str, model, query_id_map: Dict[str, str], registry=None):
        """Return standard index formula visitor (uses same_moment)."""
        return IndexFormulaToOWLVisitor(base_iri, model, query_id_map, registry)


class EquivFullCardinalityStrategy(SameMomentStrategy):
    """
    Strategy 2: Full closure with cardinality constraints.

    - Property: same_moment (simple - NO transitivity)
    - Can optionally keep ReflexiveObjectProperty and SymmetricObjectProperty
    - Assertions: All pairs materialized (16 for 4 indices)
    - World closure: Cardinality constraints (exactly N)
    - Formula translation: []φ → same_moment only φ

    Benefit: Cardinality on simple property may work better in Konclude
    """

    def add_declarations(self, ontology: Element, serializer) -> None:
        """No extra declarations needed for equivalence relation approach."""
        pass

    def add_structural_axioms(self, ontology: Element, serializer) -> None:
        """Add same_moment property with NO transitivity (simple property for cardinality)."""
        # Declare same_moment property
        serializer._declare_object_property(ontology, "same_moment")

        # Optional: Keep reflexive and symmetric (don't conflict with cardinality)
        # These reduce the number of explicit assertions needed
        reflexive = SubElement(ontology, "ReflexiveObjectProperty")
        SubElement(reflexive, "ObjectProperty", {"IRI": serializer._iri("same_moment")})

        symmetric = SubElement(ontology, "SymmetricObjectProperty")
        SubElement(symmetric, "ObjectProperty", {"IRI": serializer._iri("same_moment")})

        # NO TransitiveObjectProperty - incompatible with cardinality

    def add_same_moment_structure(self, ontology: Element, serializer) -> None:
        """
        Materialize all same_moment pairs and add cardinality constraints.

        Full closure ensures all transitivity/reflexivity/symmetry shortcuts are explicit.
        """
        # Group indices by moment
        indices_by_moment: Dict[str, List[str]] = {}
        for moment, history in serializer._get_all_indices():
            if moment not in indices_by_moment:
                indices_by_moment[moment] = []
            indices_by_moment[moment].append(serializer._index_name(moment, history))

        # For each moment, materialize all pairs
        for moment, indices in indices_by_moment.items():
            # Assert all pairs (including reflexive)
            for i_idx in indices:
                for j_idx in indices:
                    assertion = SubElement(ontology, "ObjectPropertyAssertion")
                    SubElement(assertion, "ObjectProperty", {"IRI": serializer._iri("same_moment")})
                    SubElement(assertion, "NamedIndividual", {"IRI": serializer._iri(i_idx)})
                    SubElement(assertion, "NamedIndividual", {"IRI": serializer._iri(j_idx)})

            # Add cardinality constraint for each index
            count = len(indices)
            for index in indices:
                cardinality_axiom = SubElement(ontology, "ClassAssertion")
                # Build: same_moment exactly N Thing
                restriction = SubElement(cardinality_axiom, "ObjectExactCardinality",
                                        {"cardinality": str(count)})
                SubElement(restriction, "ObjectProperty", {"IRI": serializer._iri("same_moment")})
                SubElement(restriction, "Class", {"IRI": "http://www.w3.org/2002/07/owl#Thing"})

                # Apply to this index
                SubElement(cardinality_axiom, "NamedIndividual", {"IRI": serializer._iri(index)})

    def get_formula_visitor(self, base_iri: str, model, query_id_map: Dict[str, str], registry=None):
        """Return standard index formula visitor (uses same_moment)."""
        return IndexFormulaToOWLVisitor(base_iri, model, query_id_map, registry)


class EquivFullNominalStrategy(SameMomentStrategy):
    """
    Strategy 3: Full closure with nominal class constraints.

    - Property: same_moment (simple - NO transitivity/reflexive/symmetric)
    - Assertions: All pairs materialized (16 for 4 indices)
    - World closure: Nominal class constraint
    - Formula translation: []φ → same_moment only φ

    Purpose: Test if full materialization + nominal works better than chained + nominal
    May help identify if "extreme weirdness" is due to interaction with equivalence axioms
    """

    def add_declarations(self, ontology: Element, serializer) -> None:
        """No extra declarations needed for equivalence relation approach."""
        pass

    def add_structural_axioms(self, ontology: Element, serializer) -> None:
        """Add same_moment property as simple (no characteristics)."""
        # Declare same_moment property
        serializer._declare_object_property(ontology, "same_moment")

        # NO property characteristics - keep it completely simple

    def add_same_moment_structure(self, ontology: Element, serializer) -> None:
        """
        Materialize all same_moment pairs and add nominal class constraint.

        Tests whether full materialization works better with nominal classes.
        """
        # Group indices by moment
        indices_by_moment: Dict[str, List[str]] = {}
        for moment, history in serializer._get_all_indices():
            if moment not in indices_by_moment:
                indices_by_moment[moment] = []
            indices_by_moment[moment].append(serializer._index_name(moment, history))

        # For each moment, materialize all pairs and add nominal constraint
        for moment, indices in indices_by_moment.items():
            # Assert all pairs (including reflexive)
            for i_idx in indices:
                for j_idx in indices:
                    assertion = SubElement(ontology, "ObjectPropertyAssertion")
                    SubElement(assertion, "ObjectProperty", {"IRI": serializer._iri("same_moment")})
                    SubElement(assertion, "NamedIndividual", {"IRI": serializer._iri(i_idx)})
                    SubElement(assertion, "NamedIndividual", {"IRI": serializer._iri(j_idx)})

            # Add nominal class constraint (same as Strategy 1)
            if indices:
                closure_axiom = SubElement(ontology, "ClassAssertion")
                restriction = SubElement(closure_axiom, "ObjectAllValuesFrom")
                SubElement(restriction, "ObjectProperty", {"IRI": serializer._iri("same_moment")})

                # Create nominal class (enumeration of individuals)
                nominal = SubElement(restriction, "ObjectOneOf")
                for index in indices:
                    SubElement(nominal, "NamedIndividual", {"IRI": serializer._iri(index)})

                # Apply to first index in the equivalence class
                SubElement(closure_axiom, "NamedIndividual", {"IRI": serializer._iri(indices[0])})

    def get_formula_visitor(self, base_iri: str, model, query_id_map: Dict[str, str], registry=None):
        """Return standard index formula visitor (uses same_moment)."""
        return IndexFormulaToOWLVisitor(base_iri, model, query_id_map, registry)


class EquivFocusedCardinalityStrategy(SameMomentStrategy):
    """
    Strategy 3a: Focused closure from evaluation index with cardinality.

    - Property: same_moment (simple - can optionally keep reflexive/symmetric)
    - Assertions: Only from query evaluation indices to all indices at same moment
    - World closure: Cardinality constraints
    - Formula translation: []φ → same_moment only φ

    Benefit: Minimal assertions (4 per evaluation index) while enabling cardinality
    Limitation: Must know which indices will be query evaluation points
    """

    def __init__(self, evaluation_indices: List[str] = None):
        """
        Initialize strategy.

        Args:
            evaluation_indices: List of index names where queries will be evaluated.
                              If None, uses all indices at moment 'm' (root moment).
        """
        self.evaluation_indices = evaluation_indices

    def add_declarations(self, ontology: Element, serializer) -> None:
        """No extra declarations needed for equivalence relation approach."""
        pass

    def add_structural_axioms(self, ontology: Element, serializer) -> None:
        """Add same_moment property with optional reflexive/symmetric."""
        # Declare same_moment property
        serializer._declare_object_property(ontology, "same_moment")

        # Optional: Keep reflexive and symmetric to reduce assertions
        reflexive = SubElement(ontology, "ReflexiveObjectProperty")
        SubElement(reflexive, "ObjectProperty", {"IRI": serializer._iri("same_moment")})

        symmetric = SubElement(ontology, "SymmetricObjectProperty")
        SubElement(symmetric, "ObjectProperty", {"IRI": serializer._iri("same_moment")})

        # NO TransitiveObjectProperty

    def add_same_moment_structure(self, ontology: Element, serializer) -> None:
        """
        Add focused same_moment assertions from evaluation indices.

        Only asserts same_moment from evaluation indices to all indices at same moment.
        """
        # Group indices by moment
        indices_by_moment: Dict[str, List[str]] = {}
        for moment, history in serializer._get_all_indices():
            if moment not in indices_by_moment:
                indices_by_moment[moment] = []
            indices_by_moment[moment].append(serializer._index_name(moment, history))

        # Determine evaluation indices
        if self.evaluation_indices is None:
            # Default: use all indices at root moment 'm'
            eval_indices = indices_by_moment.get('m', [])
        else:
            eval_indices = self.evaluation_indices

        # For each moment, add focused assertions
        for moment, indices in indices_by_moment.items():
            # Find evaluation indices at this moment
            moment_eval_indices = [idx for idx in eval_indices if idx in indices]

            # Assert from each evaluation index to all indices at this moment
            for eval_idx in moment_eval_indices:
                for target_idx in indices:
                    assertion = SubElement(ontology, "ObjectPropertyAssertion")
                    SubElement(assertion, "ObjectProperty", {"IRI": serializer._iri("same_moment")})
                    SubElement(assertion, "NamedIndividual", {"IRI": serializer._iri(eval_idx)})
                    SubElement(assertion, "NamedIndividual", {"IRI": serializer._iri(target_idx)})

            # Add cardinality constraint for evaluation indices
            count = len(indices)
            for eval_idx in moment_eval_indices:
                cardinality_axiom = SubElement(ontology, "ClassAssertion")
                restriction = SubElement(cardinality_axiom, "ObjectExactCardinality",
                                        {"cardinality": str(count)})
                SubElement(restriction, "ObjectProperty", {"IRI": serializer._iri("same_moment")})
                SubElement(restriction, "Class", {"IRI": "http://www.w3.org/2002/07/owl#Thing"})

                SubElement(cardinality_axiom, "NamedIndividual", {"IRI": serializer._iri(eval_idx)})

    def get_formula_visitor(self, base_iri: str, model, query_id_map: Dict[str, str], registry=None):
        """Return standard index formula visitor (uses same_moment)."""
        return IndexFormulaToOWLVisitor(base_iri, model, query_id_map, registry)


class ReifiedMomentsNominalStrategy(SameMomentStrategy):
    """
    Strategy 4: Reified moments with nominal class constraints.

    - Moment individuals: m (separate from indices)
    - Properties: has_index (moment → index), index_of (index → moment, functional)
    - Assertions: Direct m has_index relationships
    - World closure: Nominal class on moment
    - Formula translation: []φ → index_of only (has_index only φ)

    No equivalence relation needed - the moment IS the reified equivalence class.
    """

    def add_declarations(self, ontology: Element, serializer) -> None:
        """Declare moment individuals for reified moments approach."""
        # Get all unique moments
        moments = set()
        for moment, history in serializer._get_all_indices():
            moments.add(moment)

        # Declare each moment as an individual
        for moment in sorted(moments):
            serializer._declare_individual(ontology, moment)

    def add_structural_axioms(self, ontology: Element, serializer) -> None:
        """Add has_index and index_of properties with characteristics."""
        # Declare has_index property (moment → index)
        serializer._declare_object_property(ontology, "has_index")

        # Declare index_of property (index → moment)
        serializer._declare_object_property(ontology, "index_of")

        # index_of is functional (each index belongs to exactly one moment)
        functional = SubElement(ontology, "FunctionalObjectProperty")
        SubElement(functional, "ObjectProperty", {"IRI": serializer._iri("index_of")})

        # NOTE: Inverse property assertion removed - may cause issues with Konclude
        # inverse = SubElement(ontology, "InverseObjectProperties")
        # SubElement(inverse, "ObjectProperty", {"IRI": serializer._iri("has_index")})
        # SubElement(inverse, "ObjectProperty", {"IRI": serializer._iri("index_of")})

    def add_same_moment_structure(self, ontology: Element, serializer) -> None:
        """
        Add has_index/index_of assertions and nominal class constraint.

        No equivalence relation - moment individuals directly connect to their indices.
        """
        # Group indices by moment
        indices_by_moment: Dict[str, List[str]] = {}
        for moment, history in serializer._get_all_indices():
            if moment not in indices_by_moment:
                indices_by_moment[moment] = []
            indices_by_moment[moment].append(serializer._index_name(moment, history))

        # For each moment, add has_index and index_of assertions
        for moment, indices in indices_by_moment.items():
            # Assert: moment has_index each_index
            for index in indices:
                has_index_assertion = SubElement(ontology, "ObjectPropertyAssertion")
                SubElement(has_index_assertion, "ObjectProperty", {"IRI": serializer._iri("has_index")})
                SubElement(has_index_assertion, "NamedIndividual", {"IRI": serializer._iri(moment)})
                SubElement(has_index_assertion, "NamedIndividual", {"IRI": serializer._iri(index)})

                # Assert: each_index index_of moment
                index_of_assertion = SubElement(ontology, "ObjectPropertyAssertion")
                SubElement(index_of_assertion, "ObjectProperty", {"IRI": serializer._iri("index_of")})
                SubElement(index_of_assertion, "NamedIndividual", {"IRI": serializer._iri(index)})
                SubElement(index_of_assertion, "NamedIndividual", {"IRI": serializer._iri(moment)})

            # Add nominal class constraint to close the world
            # moment ∈ (has_index only {indices at this moment})
            if indices:
                closure_axiom = SubElement(ontology, "ClassAssertion")
                restriction = SubElement(closure_axiom, "ObjectAllValuesFrom")
                SubElement(restriction, "ObjectProperty", {"IRI": serializer._iri("has_index")})

                # Create nominal class (enumeration of index individuals)
                nominal = SubElement(restriction, "ObjectOneOf")
                for index in indices:
                    SubElement(nominal, "NamedIndividual", {"IRI": serializer._iri(index)})

                # Apply to moment
                SubElement(closure_axiom, "NamedIndividual", {"IRI": serializer._iri(moment)})

    def get_formula_visitor(self, base_iri: str, model, query_id_map: Dict[str, str], registry=None):
        """Return reified moments formula visitor (uses index_of/has_index)."""
        return IndexFormulaToOWLVisitorReified(base_iri, model, query_id_map, registry)


class ReifiedMomentsCardinalityStrategy(SameMomentStrategy):
    """
    Strategy 5: Reified moments with cardinality constraints.

    - Moment individuals: m (separate from indices)
    - Properties: has_index (moment → index), index_of (index → moment, functional)
    - Assertions: Direct m has_index relationships
    - World closure: Cardinality constraint on moment
    - Formula translation: []φ → index_of only (has_index only φ)

    Benefit: Cardinality on simple property, cleaner than nominal classes.
    May work better in Konclude.
    """

    def add_declarations(self, ontology: Element, serializer) -> None:
        """Declare moment individuals for reified moments approach."""
        # Get all unique moments
        moments = set()
        for moment, history in serializer._get_all_indices():
            moments.add(moment)

        # Declare each moment as an individual
        for moment in sorted(moments):
            serializer._declare_individual(ontology, moment)

    def add_structural_axioms(self, ontology: Element, serializer) -> None:
        """Add has_index and index_of properties with characteristics."""
        # Declare has_index property (moment → index)
        serializer._declare_object_property(ontology, "has_index")

        # Declare index_of property (index → moment)
        serializer._declare_object_property(ontology, "index_of")

        # index_of is functional (each index belongs to exactly one moment)
        functional = SubElement(ontology, "FunctionalObjectProperty")
        SubElement(functional, "ObjectProperty", {"IRI": serializer._iri("index_of")})

        # NOTE: Inverse property assertion removed - may cause issues with Konclude
        # inverse = SubElement(ontology, "InverseObjectProperties")
        # SubElement(inverse, "ObjectProperty", {"IRI": serializer._iri("has_index")})
        # SubElement(inverse, "ObjectProperty", {"IRI": serializer._iri("index_of")})

    def add_same_moment_structure(self, ontology: Element, serializer) -> None:
        """
        Add has_index/index_of assertions and cardinality constraint.

        Uses cardinality on simple property (has_index) instead of nominal classes.
        """
        # Group indices by moment
        indices_by_moment: Dict[str, List[str]] = {}
        for moment, history in serializer._get_all_indices():
            if moment not in indices_by_moment:
                indices_by_moment[moment] = []
            indices_by_moment[moment].append(serializer._index_name(moment, history))

        # For each moment, add has_index and index_of assertions
        for moment, indices in indices_by_moment.items():
            # Assert: moment has_index each_index
            for index in indices:
                has_index_assertion = SubElement(ontology, "ObjectPropertyAssertion")
                SubElement(has_index_assertion, "ObjectProperty", {"IRI": serializer._iri("has_index")})
                SubElement(has_index_assertion, "NamedIndividual", {"IRI": serializer._iri(moment)})
                SubElement(has_index_assertion, "NamedIndividual", {"IRI": serializer._iri(index)})

                # Assert: each_index index_of moment
                index_of_assertion = SubElement(ontology, "ObjectPropertyAssertion")
                SubElement(index_of_assertion, "ObjectProperty", {"IRI": serializer._iri("index_of")})
                SubElement(index_of_assertion, "NamedIndividual", {"IRI": serializer._iri(index)})
                SubElement(index_of_assertion, "NamedIndividual", {"IRI": serializer._iri(moment)})

            # Add cardinality constraint to close the world
            # moment ∈ (has_index exactly N Thing)
            count = len(indices)
            cardinality_axiom = SubElement(ontology, "ClassAssertion")
            restriction = SubElement(cardinality_axiom, "ObjectExactCardinality",
                                    {"cardinality": str(count)})
            SubElement(restriction, "ObjectProperty", {"IRI": serializer._iri("has_index")})
            SubElement(restriction, "Class", {"IRI": "http://www.w3.org/2002/07/owl#Thing"})

            # Apply to moment
            SubElement(cardinality_axiom, "NamedIndividual", {"IRI": serializer._iri(moment)})

    def get_formula_visitor(self, base_iri: str, model, query_id_map: Dict[str, str], registry=None):
        """Return reified moments formula visitor (uses index_of/has_index)."""
        return IndexFormulaToOWLVisitorReified(base_iri, model, query_id_map, registry)
