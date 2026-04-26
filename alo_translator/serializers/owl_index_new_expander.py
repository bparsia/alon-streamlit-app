"""
OWL Index serializer using NEW ExpanderTransformer + OwlSerializer for TBox.

Hybrid approach:
- ABox: Uses existing OWLIndexSerializer infrastructure (individuals, properties, assertions)
- TBox: Uses NEW ExpanderTransformer + OwlSerializer (query class definitions)
"""

from typing import Dict
from xml.etree.ElementTree import Element, SubElement
from lark import Lark

from .owl_index import OWLIndexSerializer
from ..parsers.expander_transformer import ExpanderTransformer
from ..serializers.owl_serializer import OwlSerializer


class OWLIndexNewExpanderSerializer(OWLIndexSerializer):
    """
    Extended OWLIndexSerializer that uses the NEW expansion pipeline.

    Overrides:
    - _add_query_classes(): Use ExpanderTransformer + OwlSerializer
    - _add_expansion_axioms(): Generate expansion axioms from new system
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Load grammar for new expander
        grammar_path = "alo_translator/parsers/alon_grammar_clean.lark"
        with open(grammar_path) as f:
            grammar = f.read()
        self.parser = Lark(grammar, start='start', parser='lalr')

        # OWL serializer will be created after expander (to get name_to_formula mapping)
        self.owl_serializer = None
        self.expander = None  # Track expander for name mappings

        # Track query to name mapping
        self.query_name_map: Dict[str, str] = {}  # formula_string -> query_id
        self.query_expansions: Dict[str, str] = {}  # query_id -> expansion_name

    def _make_expander(self) -> ExpanderTransformer:
        """Factory for the ExpanderTransformer.  Subclasses can override to
        inject evaluation_moment or use a different transformer class."""
        return ExpanderTransformer(self.parser, self.model)

    def _add_query_classes(self, ontology: Element):
        """
        Add query class definitions using NEW ExpanderTransformer + OwlSerializer.

        For each query:
        1. Parse with Lark
        2. Expand with ExpanderTransformer (generates axioms) - SHARED expander for all queries
        3. Serialize axioms with OwlSerializer (created with expander's name_to_formula mapping)
        4. Extract SubClassOf elements and add to ontology
        5. Add rdfs:label annotation assertions
        """
        # Step 1: Create a single expander for all queries (shares q-name counter)
        self.expander = self._make_expander()

        # Step 2: Process each query
        for query in self.model.queries:
            query_id = query.query_id
            if not query_id:
                self.query_counter += 1
                query_id = f"q{self.query_counter:02d}"

            self.query_name_map[query.formula_string] = query_id

            # Declare the query class
            self._declare_class(ontology, query_id, query.formula_string)

            try:
                # Parse and expand formula
                formula_str = query.formula_string
                print(f"DEBUG: Parsing query {query_id}: {formula_str}")
                tree = self.parser.parse(formula_str)

                # Expand with shared expander
                result_name = self.expander.transform(tree)
                print(f"DEBUG: Query {query_id} expanded to {result_name}")

                # Store mapping for later - we'll add SubClassOf axioms after OWL serializer is created
                self.query_expansions[query_id] = result_name

            except Exception as e:
                # Print the actual formula string that failed
                print(f"Warning: Could not expand query '{query_id}': {e}")
                annotation = SubElement(ontology, "AnnotationAssertion")
                SubElement(annotation, "AnnotationProperty",
                          {"IRI": f"{self.RDFS_NS}comment"})
                SubElement(annotation, "IRI", text=self._iri(query_id))
                SubElement(annotation, "Literal",
                          text=f"Expansion failed: {str(e)}")

        # Step 3: Create OWL serializer with name_to_formula mapping from expander
        print(f"DEBUG: Creating OWL serializer with {len(self.expander.name_to_formula)} formula mappings")
        self.owl_serializer = OwlSerializer(
            base_iri=self.BASE_IRI,
            name_to_formula=self.expander.name_to_formula
        )

        # Step 4: Serialize all expansion axioms to OWL
        print(f"DEBUG: Serializing {len(self.expander.axioms)} expansion axioms")
        for axiom in self.expander.axioms:
            # Skip trivial or empty axioms
            if '=>' in axiom:
                parts = axiom.split('=>')
                if len(parts) == 2:
                    lhs = parts[0].strip()
                    rhs = parts[1].strip()
                    # Skip if either side is empty or they're identical (trivial axiom)
                    if not lhs or not rhs or lhs == rhs or lhs == '()':
                        print(f"DEBUG: Skipping invalid/trivial axiom: {axiom[:60]}")
                        continue

            axiom_tree = self.parser.parse(axiom)
            self.owl_serializer.transform(axiom_tree)

        # Step 5: Add all accumulated SubClassOf axioms from OwlSerializer
        print(f"DEBUG: Adding {len(self.owl_serializer.axioms)} SubClassOf axioms")
        for i, axiom_str in enumerate(self.owl_serializer.axioms):
            if i == 0:  # Debug first axiom fully
                print(f"DEBUG: Full axiom string:")
                print(axiom_str)
                print()
            # Parse the XML string to Element
            from xml.etree.ElementTree import fromstring
            try:
                # Extract the content between <SubClassOf> tags
                import re
                match = re.search(r'<SubClassOf>\s*(.*?)\s*</SubClassOf>', axiom_str, re.DOTALL)
                if match:
                    inner_content = match.group(1).strip()
                    # Parse as proper OWL XML
                    wrapped = f'<SubClassOf xmlns="{self.OWL_NS}">{inner_content}</SubClassOf>'
                    subclass_elem = fromstring(wrapped)
                    ontology.append(subclass_elem)
                else:
                    print(f"Warning: Could not extract SubClassOf content from axiom")
                    print(f"Axiom: {axiom_str[:400]}")
            except Exception as e:
                print(f"Warning: Could not parse axiom XML: {e}")
                print(f"Axiom: {axiom_str[:400]}")

        # Step 6: Add rdfs:label annotation assertions
        print(f"DEBUG: Adding {len(self.owl_serializer.annotations)} rdfs:label annotations")
        for i, annotation_str in enumerate(self.owl_serializer.annotations):
            try:
                # Parse annotation XML string
                wrapped = f'<AnnotationAssertion xmlns="{self.OWL_NS}" xmlns:rdfs="{self.RDFS_NS}">{annotation_str}</AnnotationAssertion>'
                # Extract inner content
                import re
                match = re.search(r'<AnnotationAssertion>\s*(.*?)\s*</AnnotationAssertion>', annotation_str, re.DOTALL)
                if match:
                    inner_content = match.group(1).strip()
                    wrapped = f'<AnnotationAssertion xmlns="{self.OWL_NS}" xmlns:rdfs="{self.RDFS_NS}">{inner_content}</AnnotationAssertion>'
                    annotation_elem = fromstring(wrapped)
                    ontology.append(annotation_elem)
                else:
                    print(f"Warning: Could not extract AnnotationAssertion content")
            except Exception as e:
                print(f"Warning: Could not parse annotation XML: {e}")
                if i < 3:  # Show first few for debugging
                    print(f"Annotation: {annotation_str[:400]}")

        # Step 7: Add SubClassOf axioms connecting query IDs to their expansions
        print(f"DEBUG: Adding {len(self.query_expansions)} query definition axioms")
        from xml.etree.ElementTree import fromstring
        for query_id, expansion_name in self.query_expansions.items():
            # Parse the expansion_name to get OWL class element
            # If expansion_name is a simple name (like "Xq" or "q1"), create a Class element
            # Otherwise, parse it as a formula
            try:
                # Try to parse as a formula first
                expansion_tree = self.parser.parse(expansion_name)
                expansion_owl = self.owl_serializer.transform(expansion_tree)

                # Create SubClassOf axiom: expansion_owl SubClassOf query_id
                # i.e. if m_h1 : expansion_name then m_h1 : query_id (query satisfied)
                wrapped = f'<SubClassOf xmlns="{self.OWL_NS}">\n        {expansion_owl}\n        <Class IRI="{self.BASE_IRI}{query_id}"/>\n    </SubClassOf>'
                subclass_elem = fromstring(wrapped)
                ontology.append(subclass_elem)
                print(f"DEBUG: Added definition {expansion_name[:50]} SubClassOf {query_id}")
            except Exception as e:
                print(f"Warning: Could not create query definition for {query_id}: {e}")

    def _add_expansion_axioms(self, ontology: Element):
        """
        Add expansion axiom declarations.

        The NEW system already handles expansions in _add_query_classes(),
        so this method just ensures all intermediate classes are declared.
        """
        # Declare all classes tracked by the OWL serializer
        for class_name in self.owl_serializer.classes:
            # Check if not already declared (queries are declared in _add_query_classes)
            if class_name not in self.query_name_map.values():
                # Check if it's an action class (already declared in _add_declarations)
                is_action = any(
                    class_name == f"{action_type}{agent_id}"
                    for agent_id, action_types in self.model.agents_actions.items()
                    for action_type in action_types
                )
                # Check if it's an opposing class (already declared)
                is_opposing = class_name.startswith("Opp2")

                # Check if it's a proposition class (already declared)
                is_prop = any(
                    class_name == prop
                    for result in self.model.results
                    for prop in result.true_propositions
                )

                if not (is_action or is_opposing or is_prop):
                    # This is an intermediate formula name - declare it
                    self._declare_class(ontology, class_name, f"Formula {class_name}")
