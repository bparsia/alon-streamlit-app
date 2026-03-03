"""
OWL Index-based serializer - uses moment/history pairs as individuals.

This serializer uses the standard Kripke semantics for branching time where
individuals represent moment-history pairs (indices) rather than just moments.

Key differences from ABox approach:
- Individuals: m_h1, m_h2, etc. (moment/history pairs)
- Properties: same_moment (equivalence relation), succ (successor)
- Actions: Indices are members of action classes (not at result moments)
- Propositions: True at the indices where they hold

Example for 2 histories:
    m_h1 same_moment m_h2
    m_h1 succ m1_h1
    m_h2 succ m2_h2
    m_h1 memberOf CGA_h1
    m_h2 memberOf CGA_h2
"""

from typing import List, Set, Dict, Tuple, Optional
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from .base import Serializer
from .index_formula_visitor import IndexFormulaToOWLVisitor
from ..model.core import ALOModel, Action, GroupAction, OpposingRelation


class OWLIndexSerializer(Serializer):
    """
    Serializes ALOn models to OWL/XML using index-based approach.

    Translation:
    - Moment/history pairs as individuals (m_h1, m_h2, etc.)
    - same_moment: equivalence relation connecting indices at same moment
    - succ: successor relation between indices
    - Actions as classes with indices as members
    - Propositions as classes with indices as members
    - Query classes defined using index-based semantics
    """

    BASE_IRI = "http://www.semanticweb.org/alon#"
    OWL_NS = "http://www.w3.org/2002/07/owl#"
    RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"

    def __init__(self, model: ALOModel,
                 strategy: Optional['SameMomentStrategy'] = None,
                 use_subclass_axioms: bool = True):
        """Initialize the serializer.

        Args:
            model: The ALOn model to serialize
            strategy: Strategy for same_moment representation (default: EquivChainedNominalStrategy)
            use_subclass_axioms: If True (default), use SubClassOf axioms for queries
        """
        super().__init__(model)
        # Import here to avoid circular dependency
        if strategy is None:
            from .index_strategies import EquivChainedNominalStrategy
            strategy = EquivChainedNominalStrategy()
        self.strategy = strategy
        self.use_subclass_axioms = use_subclass_axioms
        self.query_counter = 0
        self.cga_to_history: Dict[tuple, str] = {}  # Map CGA to history name
        self.history_to_cga: Dict[str, GroupAction] = {}  # Map history name to CGA
        self._declared_classes: Set[str] = set()  # Guard against duplicate declarations

    def serialize(self) -> str:
        """Serialize the model to OWL/XML."""
        # Build ontology
        ontology = self._build_ontology()

        # Convert to string
        rough_string = tostring(ontology, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        xml_string = reparsed.toprettyxml(indent="    ")

        # Post-process: Remove ns0: prefix and xmlns:ns0 declaration
        # This fixes an issue where minidom adds ns0 prefix for elements
        # that were parsed with their own xmlns declaration
        import re
        xml_string = re.sub(r'xmlns:ns0="[^"]*"\s*', '', xml_string)
        xml_string = re.sub(r'ns0:', '', xml_string)

        return xml_string

    def _build_ontology(self) -> Element:
        """Build the complete OWL ontology."""
        # Create root ontology element
        ontology = Element("Ontology",
                          xmlns=self.OWL_NS,
                          attrib={
                              f"{{{self.OWL_NS}}}ontologyIRI": self.BASE_IRI,
                              f"{{{self.RDF_NS}}}about": self.BASE_IRI
                          })

        # Add declarations
        self._add_declarations(ontology)

        # Strategy-specific declarations (e.g., moment individuals for reified strategies)
        self.strategy.add_declarations(ontology, self)

        # Strategy-specific structural axioms (same_moment property and characteristics)
        self.strategy.add_structural_axioms(ontology, self)

        # Add succ structural axioms (strategy-independent)
        self._add_succ_structural_axioms(ontology)

        # Add opposing axioms
        self._add_opposing_axioms(ontology)

        # Add action disjointness axioms
        self._add_action_disjointness(ontology)

        # Add index individuals
        self._add_indices(ontology)

        # Add AllDifferent axiom for all individuals (closed world for individuals)
        self._add_all_different(ontology)

        # Strategy-specific same_moment structure (assertions + world closure)
        self.strategy.add_same_moment_structure(ontology, self)

        # Add succ assertions
        self._add_succ_assertions(ontology)

        # Add action assertions (indices as members of action classes)
        self._add_action_assertions(ontology)

        # Add proposition assertions
        self._add_proposition_assertions(ontology)

        # Add query classes
        self._add_query_classes(ontology)

        # Add expansion axioms for defined operators
        self._add_expansion_axioms(ontology)

        return ontology

    def _iri(self, name: str) -> str:
        """Generate full IRI for a name."""
        return f"{self.BASE_IRI}{name}"

    def _declare_class(self, ontology: Element, class_name: str, label: str = None):
        """Declare an OWL class (idempotent: skips if already declared)."""
        if class_name in self._declared_classes:
            return
        self._declared_classes.add(class_name)

        decl = SubElement(ontology, "Declaration")
        SubElement(decl, "Class", {"IRI": self._iri(class_name)})

        if label:
            annotation = SubElement(ontology, "AnnotationAssertion")
            SubElement(annotation, "AnnotationProperty",
                      {"IRI": f"{self.RDFS_NS}label"})
            SubElement(annotation, "IRI", text=self._iri(class_name))
            SubElement(annotation, "Literal", text=label)

    def _declare_object_property(self, ontology: Element, prop_name: str):
        """Declare an object property."""
        decl = SubElement(ontology, "Declaration")
        SubElement(decl, "ObjectProperty", {"IRI": self._iri(prop_name)})

    def _declare_individual(self, ontology: Element, ind_name: str):
        """Declare a named individual."""
        decl = SubElement(ontology, "Declaration")
        SubElement(decl, "NamedIndividual", {"IRI": self._iri(ind_name)})

    def _add_declarations(self, ontology: Element):
        """Add all class, property, and individual declarations."""
        # Declare same_moment and succ properties
        self._declare_object_property(ontology, "same_moment")
        self._declare_object_property(ontology, "succ")

        # Declare action classes
        for agent_id, action_types in self.model.agents_actions.items():
            for action_type in action_types:
                action_name = f"{action_type}{agent_id}"
                self._declare_class(ontology, action_name, f"Action {action_name}")

        # Declare proposition classes
        all_props = set()
        for result in self.model.results:
            all_props.update(result.true_propositions)
        for prop in all_props:
            self._declare_class(ontology, prop, f"Proposition {prop}")

        # Declare opposing classes for ALL actions (needed for closed-world on opposing)
        # Even actions with no explicit opposings need Opp2X classes for query evaluation
        for action in self.model.get_all_actions():
            self._declare_class(ontology, f"Opp2{action}", f"Opposing to {action}")

        # Declare query classes (will be added later)
        for query in self.model.queries:
            if query.query_id:
                self._declare_class(ontology, query.query_id, query.formula_string)

    def _build_cga_mappings(self):
        """Build mappings between CGAs and history names."""
        # Get all complete group actions
        complete_gas = self.model.generate_complete_group_actions()

        history_counter = 1

        for cga in complete_gas:
            # Create a hashable key for this CGA
            cga_key = tuple(sorted(cga.actions.items()))

            # Check if this CGA has a named history
            hist_name = None
            for name, named_cga in self.model.named_histories.items():
                if named_cga.actions == cga.actions:
                    hist_name = name
                    break

            # If no named history, generate h2, h3, etc.
            if hist_name is None:
                while f"h{history_counter}" in self.model.named_histories:
                    history_counter += 1
                hist_name = f"h{history_counter}"
                history_counter += 1

            # Store mappings
            self.cga_to_history[cga_key] = hist_name
            self.history_to_cga[hist_name] = cga

    def _get_all_indices(self) -> List[Tuple[str, str]]:
        """
        Get all moment/history index pairs.

        Returns list of (moment_name, history_name) tuples.
        For 1-step models: [('m', 'h1'), ('m', 'h2'), ('m1', 'h1'), ('m2', 'h2'), ...]

        Generates indices for ALL possible complete group actions, not just named histories.
        """
        if not self.history_to_cga:
            self._build_cga_mappings()

        indices = []
        history_names = list(self.history_to_cga.keys())

        # Root moment with all histories (one index per CGA at root moment)
        for history_name in history_names:
            indices.append(('m', history_name))

        # Successor moments (one per history in 1-step models)
        for i, history_name in enumerate(history_names, 1):
            successor_moment = f"m{i}"
            indices.append((successor_moment, history_name))

        return indices

    def _index_name(self, moment: str, history: str) -> str:
        """Generate index individual name from moment and history."""
        return f"{moment}_{history}"

    def _add_succ_structural_axioms(self, ontology: Element):
        """Add axioms defining succ property (strategy-independent)."""
        # succ is functional (each index has at most one successor)
        functional = SubElement(ontology, "FunctionalObjectProperty")
        SubElement(functional, "ObjectProperty", {"IRI": self._iri("succ")})

        # succ is serial (Thing => succ some Thing)
        # Every individual has at least one successor
        serial_axiom = SubElement(ontology, "SubClassOf")
        SubElement(serial_axiom, "Class", {"IRI": "http://www.w3.org/2002/07/owl#Thing"})
        succ_some_thing = SubElement(serial_axiom, "ObjectSomeValuesFrom")
        SubElement(succ_some_thing, "ObjectProperty", {"IRI": self._iri("succ")})
        SubElement(succ_some_thing, "Class", {"IRI": "http://www.w3.org/2002/07/owl#Thing"})

    def _add_opposing_axioms(self, ontology: Element):
        """Add Opp2X classes and subsumption axioms for opposing relations."""
        # Group opposings by opposed action
        opposing_map: Dict[str, List] = {}
        for opp in self.model.opposings:
            opposed_str = str(opp.opposed_action)
            if opposed_str not in opposing_map:
                opposing_map[opposed_str] = []
            opposing_map[opposed_str].append(opp.opposing_action)

        # For each opposed action, create Opp2X class and subsumption axioms
        for opposed_str, opposing_actions in opposing_map.items():
            opp_class = f"Opp2{opposed_str}"

            # Each opposing action is subclass of Opp2X
            for opposing_action in opposing_actions:
                opposing_str = str(opposing_action)

                subclass = SubElement(ontology, "SubClassOf")
                SubElement(subclass, "Class", {"IRI": self._iri(opposing_str)})
                SubElement(subclass, "Class", {"IRI": self._iri(opp_class)})

    def _add_action_disjointness(self, ontology: Element):
        """Add disjointness axioms: each agent can only do one action at a time."""
        # For each agent, their actions are pairwise disjoint
        for agent_id, action_types in self.model.agents_actions.items():
            if len(action_types) > 1:
                # Create pairwise disjoint classes axiom
                disjoint = SubElement(ontology, "DisjointClasses")
                for action_type in action_types:
                    action_name = f"{action_type}{agent_id}"
                    SubElement(disjoint, "Class", {"IRI": self._iri(action_name)})

    def _add_indices(self, ontology: Element):
        """Declare all index individuals."""
        for moment, history in self._get_all_indices():
            index_name = self._index_name(moment, history)
            self._declare_individual(ontology, index_name)

    def _add_all_different(self, ontology: Element):
        """
        Add AllDifferent axiom for all individuals.

        This enforces unique name assumption (closed world for individuals).
        """
        all_indices = [self._index_name(m, h) for m, h in self._get_all_indices()]

        if len(all_indices) > 1:
            all_diff = SubElement(ontology, "DifferentIndividuals")
            for index in all_indices:
                SubElement(all_diff, "NamedIndividual", {"IRI": self._iri(index)})

    def _add_succ_assertions(self, ontology: Element):
        """
        Add succ assertions between indices.

        For each history, connect its root index to its successor index.
        """
        if not self.history_to_cga:
            self._build_cga_mappings()

        for i, history_name in enumerate(self.history_to_cga.keys(), 1):
            root_index = self._index_name('m', history_name)
            succ_index = self._index_name(f'm{i}', history_name)

            assertion = SubElement(ontology, "ObjectPropertyAssertion")
            SubElement(assertion, "ObjectProperty", {"IRI": self._iri("succ")})
            SubElement(assertion, "NamedIndividual", {"IRI": self._iri(root_index)})
            SubElement(assertion, "NamedIndividual", {"IRI": self._iri(succ_index)})

    def _add_action_assertions(self, ontology: Element):
        """
        Add action class assertions for indices.

        Each index at the root moment is a member of the action classes
        corresponding to the complete group action for that history.
        """
        if not self.history_to_cga:
            self._build_cga_mappings()

        for history_name, group_action in self.history_to_cga.items():
            root_index = self._index_name('m', history_name)

            # Add assertion for each action in the group action
            for action in group_action.to_action_list():
                action_class = str(action)  # e.g., "sd1"

                assertion = SubElement(ontology, "ClassAssertion")
                SubElement(assertion, "Class", {"IRI": self._iri(action_class)})
                SubElement(assertion, "NamedIndividual", {"IRI": self._iri(root_index)})

            # Add negative assertions for Opp2 classes (closed-world assumption)
            self._add_opposing_negative_assertions(ontology, root_index, group_action)

    def _add_opposing_negative_assertions(self, ontology: Element, index_name: str,
                                          cga: GroupAction):
        """
        Add negative class assertions for Opp2X classes when the action is unopposed.

        For each opposing relation defining Opp2X, check if any action in the CGA
        is a member of Opp2X (i.e., opposes X). If not, explicitly assert that
        the index is NOT in Opp2X.
        """
        # Build map: opp_class_name -> set of action strings that are subclasses
        opp_class_members: Dict[str, Set] = {}

        # From explicit opposings in model
        for opp in self.model.opposings:
            opposed_str = str(opp.opposed_action)
            opp_class = f"Opp2{opposed_str}"

            if opp_class not in opp_class_members:
                opp_class_members[opp_class] = set()

            opposing_str = str(opp.opposing_action)
            opp_class_members[opp_class].add(opposing_str)

        # Also include Opp2X classes for all actions
        for action in self.model.get_all_actions():
            opp_class = f"Opp2{action}"
            if opp_class not in opp_class_members:
                opp_class_members[opp_class] = set()

        # Get all actions performed in this CGA
        cga_actions = set()
        for action in cga.to_action_list():
            cga_actions.add(str(action))

        # For each Opp2X class, check if CGA contains any opposing action
        for opp_class, members in opp_class_members.items():
            has_opposing = bool(cga_actions & members)

            if not has_opposing:
                # No opposing action present - add negative assertion
                neg_assertion = SubElement(ontology, "ClassAssertion")
                obj_compl = SubElement(neg_assertion, "ObjectComplementOf")
                SubElement(obj_compl, "Class", {"IRI": self._iri(opp_class)})
                SubElement(neg_assertion, "NamedIndividual", {"IRI": self._iri(index_name)})

    def _add_proposition_assertions(self, ontology: Element):
        """
        Add proposition class assertions for indices.

        Each successor index is a member of the proposition classes
        that are true in that history's result, and explicitly NOT a member
        of propositions that are false (closed-world assumption).
        """
        if not self.history_to_cga:
            self._build_cga_mappings()

        # Get all propositions in the model
        all_props = set(self.model.get_all_propositions())

        for i, history_name in enumerate(self.history_to_cga.keys(), 1):
            succ_index = self._index_name(f'm{i}', history_name)

            # Find the result for this history
            true_props = set()
            for result in self.model.results:
                if result.history_name == history_name:
                    true_props = set(result.true_propositions)
                    # Add positive assertions
                    for prop in result.true_propositions:
                        assertion = SubElement(ontology, "ClassAssertion")
                        SubElement(assertion, "Class", {"IRI": self._iri(prop)})
                        SubElement(assertion, "NamedIndividual", {"IRI": self._iri(succ_index)})
                    break

            # Add negative assertions for propositions that are NOT true
            false_props = all_props - true_props
            for prop in false_props:
                neg_assertion = SubElement(ontology, "ClassAssertion")
                obj_compl = SubElement(neg_assertion, "ObjectComplementOf")
                SubElement(obj_compl, "Class", {"IRI": self._iri(prop)})
                SubElement(neg_assertion, "NamedIndividual", {"IRI": self._iri(succ_index)})

    def _add_query_classes(self, ontology: Element):
        """Add query class definitions using index-based semantics."""
        # Build query ID map
        query_id_map: Dict[str, str] = {}
        for query in self.model.queries:
            if query.query_id:
                query_id = query.query_id
            else:
                self.query_counter += 1
                query_id = f"q{self.query_counter:02d}"
            query_id_map[query.formula_string] = query_id

        # Create visitor for index-based translation (strategy-specific)
        # If model has a registry, pass it to the visitor so it can resolve NamedFormula references
        registry = getattr(self.model, 'formula_registry', None)
        visitor = self.strategy.get_formula_visitor(
            self.BASE_IRI,
            self.model,
            query_id_map=query_id_map,
            registry=registry
        )

        # Translate each query
        for query in self.model.queries:
            query_id = query.query_id or query_id_map.get(query.formula_string)

            # Declare the query class
            self._declare_class(ontology, query_id, query.formula_string)

            # Translate using IndexFormulaToOWLVisitor
            try:
                if not hasattr(query, 'expanded_ast') or query.expanded_ast is None:
                    raise ValueError(f"Query '{query_id}' missing expanded_ast - run parse_toml() from builder module")

                # If we have a registry, use NamedFormula reference for hierarchical expansion
                if hasattr(self.model, 'formula_registry') and self.model.formula_registry is not None:
                    from ..model.formula import NamedFormula
                    # Use NamedFormula to reference the registered formula
                    # Get the OWL name from the formula AST
                    formula_key = query.formula_ast.to_owl_name()
                    owl_expr = visitor.translate(NamedFormula(formula_key))
                else:
                    # No registry - translate inline expansion
                    owl_expr = visitor.translate(query.expanded_ast)

                # Add query axiom
                if self.use_subclass_axioms:
                    subclass = SubElement(ontology, "SubClassOf")
                    subclass.append(owl_expr)
                    SubElement(subclass, "Class", {"IRI": self._iri(query_id)})
                else:
                    equiv_classes = SubElement(ontology, "EquivalentClasses")
                    SubElement(equiv_classes, "Class", {"IRI": self._iri(query_id)})
                    equiv_classes.append(owl_expr)

            except NotImplementedError as e:
                # Some formula types not yet supported in index semantics
                annotation = SubElement(ontology, "AnnotationAssertion")
                SubElement(annotation, "AnnotationProperty",
                          {"IRI": f"{self.RDFS_NS}comment"})
                SubElement(annotation, "IRI", text=self._iri(query_id))
                SubElement(annotation, "Literal",
                          text=f"Not yet supported: {str(e)}")
            except Exception as e:
                print(f"Warning: Could not translate query '{query_id}': {e}")
                annotation = SubElement(ontology, "AnnotationAssertion")
                SubElement(annotation, "AnnotationProperty",
                          {"IRI": f"{self.RDFS_NS}comment"})
                SubElement(annotation, "IRI", text=self._iri(query_id))
                SubElement(annotation, "Literal",
                          text=f"Translation failed: {str(e)}")

    def _add_expansion_axioms(self, ontology: Element):
        """
        Add SubClassOf axioms for formula expansions.

        For each expanded formula in the registry, generates:
        - Declaration for the formula class (if not already declared)
        - SubClassOf axiom: expansion ⊑ name (correct direction!)
        - rdfs:label annotation with human-readable source formula

        Only generates axioms if model has formula_registry.
        """
        # Check if model has registry
        if not hasattr(self.model, 'formula_registry'):
            return  # No expansions to add

        registry = self.model.formula_registry

        # Build query ID map for visitor context
        query_id_map: Dict[str, str] = {}
        for query in self.model.queries:
            if query.query_id:
                query_id = query.query_id
            else:
                self.query_counter += 1
                query_id = f"q{self.query_counter:02d}"
            query_id_map[query.formula_string] = query_id

        # Create visitor for translating expansions to OWL
        # Pass registry so it can resolve NamedFormula references
        expansion_visitor = self.strategy.get_formula_visitor(
            self.BASE_IRI,
            self.model,
            query_id_map=query_id_map,
            registry=registry
        )

        # Iterate through all expanded formulas in registry
        # registry.formulas is now Dict[str, FormulaNode] where:
        # - key: OWL name (e.g., "expected_sd1_q", "Xq", "free_do_sd1")
        # - value: processed expansion tree with NamedFormula references
        for owl_name, expansion_tree in registry.formulas.items():
            # Declare the formula class (if not already declared as a query)
            # Check if this name is already a query class
            is_query = any(
                (q.query_id and q.query_id == owl_name) or
                query_id_map.get(q.formula_string) == owl_name
                for q in self.model.queries
            )
            if not is_query:
                label = registry.labels.get(owl_name)
                self._declare_class(ontology, owl_name, label or owl_name)

            # Check if this is a true primitive (no expansion axiom needed)
            from ..model.formula import Prop, DoAction
            if isinstance(expansion_tree, (Prop, DoAction)):
                # True primitives don't get expansion axioms
                # They are already declared and used directly
                continue

            # Translate the expansion tree to OWL
            try:
                # The expansion_tree contains NamedFormula references for subformulas
                # and structural connectives as actual nodes (to be inlined)
                owl_expansion = expansion_visitor.translate(expansion_tree)

                # Add SubClassOf axiom: expansion ⊑ name
                # This means: "Everything satisfying the expansion is in the named class"
                # So when reasoner proves m_h1 : expansion, it infers m_h1 : name (the query)
                subclass = SubElement(ontology, "SubClassOf")
                subclass.append(owl_expansion)  # Left side: expansion (subclass)
                SubElement(subclass, "Class", {"IRI": self._iri(owl_name)})  # Right side: name (superclass)

            except NotImplementedError as e:
                # Some formula types not yet supported
                annotation = SubElement(ontology, "AnnotationAssertion")
                SubElement(annotation, "AnnotationProperty",
                          {"IRI": f"{self.RDFS_NS}comment"})
                SubElement(annotation, "IRI", text=self._iri(owl_name))
                SubElement(annotation, "Literal",
                          text=f"Expansion not yet supported: {str(e)}")
            except Exception as e:
                print(f"Warning: Could not translate expansion for '{owl_name}': {e}")
                annotation = SubElement(ontology, "AnnotationAssertion")
                SubElement(annotation, "AnnotationProperty",
                          {"IRI": f"{self.RDFS_NS}comment"})
                SubElement(annotation, "IRI", text=self._iri(owl_name))
                SubElement(annotation, "Literal",
                          text=f"Expansion translation failed: {str(e)}")
