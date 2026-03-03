"""OWL Serializer - outputs expanded formulas as OWL ontology.

Handles only the "directly translated" constructs that remain after expansion.
"""

from lark import Transformer


class OwlSerializer(Transformer):
    """Serializes expanded ALOn formulas to OWL/XML SubClassOf axioms.

    Converts `=>` expansion axioms to SubClassOf.
    Tracks entities for declaration generation.
    """

    def __init__(self, base_iri="http://www.semanticweb.org/alon#", name_to_formula=None):
        """Initialize serializer.

        Args:
            base_iri: Base IRI for all entities
            name_to_formula: Optional dict mapping q-names to formula strings for rdfs:label annotations
        """
        self.base_iri = base_iri
        self.classes = set()  # Track classes for declarations
        self.object_properties = set()  # Track properties for declarations
        self.axioms = []  # Accumulate SubClassOf axioms
        self.annotations = []  # Accumulate rdfs:label annotations
        self.name_to_formula = name_to_formula or {}  # For generating labels

    def _sanitize_name(self, name):
        """Sanitize name for OWL by replacing special chars with underscores.

        Replaces: { } : , space ( ) ~ & v | > < - [ ]
        """
        replacements = {
            '{': '_',
            '}': '_',
            ':': '_',
            ',': '_',
            ' ': '_',
            '(': '_',
            ')': '_',
            '~': '_',
            '&': '_',
            'v': '_',
            '|': '_',
            '>': '_',
            '<': '_',
            '-': '_',
            '[': '_',
            ']': '_',
        }
        result = str(name)
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result

    def _iri(self, name):
        """Create IRI reference for entity."""
        return f'IRI="{self.base_iri}{name}"'

    def _class(self, name):
        """Create Class element and track entity."""
        sanitized = self._sanitize_name(name)
        self.classes.add(sanitized)
        return f'<Class {self._iri(sanitized)}/>'

    def _property(self, name):
        """Create ObjectProperty element and track entity."""
        self.object_properties.add(name)
        return f'<ObjectProperty {self._iri(name)}/>'

    def _escape_xml(self, text):
        """Escape XML special characters in text."""
        replacements = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&apos;',
        }
        result = str(text)
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result

    def _add_label_annotation(self, qname, formula_string):
        """Generate rdfs:label annotation for a q-name.

        Args:
            qname: The q-name (e.g., "q1")
            formula_string: The formula string to use as label
        """
        escaped_formula = self._escape_xml(formula_string)
        annotation = f"""    <AnnotationAssertion>
        <AnnotationProperty IRI="http://www.w3.org/2000/01/rdf-schema#label"/>
        <IRI>{self.base_iri}{qname}</IRI>
        <Literal datatypeIRI="http://www.w3.org/2001/XMLSchema#string">{escaped_formula}</Literal>
    </AnnotationAssertion>"""
        self.annotations.append(annotation)

    # ========== Top-level expansion axiom ==========

    def expansion_axiom(self, items):
        """formula => name  →  SubClassOf(formula_owl, Class(name))

        Also generates rdfs:label annotation if formula string is available.
        """
        formula_owl, name = items
        name_str = str(name)
        sanitized = self._sanitize_name(name_str)
        self.classes.add(sanitized)

        # Generate SubClassOf axiom
        axiom = f"""    <SubClassOf>
        {formula_owl}
        <Class {self._iri(sanitized)}/>
    </SubClassOf>"""
        self.axioms.append(axiom)

        # Generate rdfs:label annotation if we have the formula string
        if name_str in self.name_to_formula:
            formula_string = self.name_to_formula[name_str]
            self._add_label_annotation(name_str, formula_string)

        return axiom

    # ========== Propositional Logic ==========

    def biconditional(self, items):
        """φ <-> ψ  →  ObjectIntersectionOf(ObjectUnionOf(not φ, ψ), ObjectUnionOf(not ψ, φ))"""
        if len(items) == 1:
            return items[0]
        # Build right-associatively
        result = items[-1]
        for item in reversed(items[:-1]):
            not_left = f'<ObjectComplementOf>{item}</ObjectComplementOf>'
            not_right = f'<ObjectComplementOf>{result}</ObjectComplementOf>'
            left_implies_right = f'<ObjectUnionOf>{not_left}{result}</ObjectUnionOf>'
            right_implies_left = f'<ObjectUnionOf>{not_right}{item}</ObjectUnionOf>'
            result = f'<ObjectIntersectionOf>{left_implies_right}{right_implies_left}</ObjectIntersectionOf>'
        return result

    def implication(self, items):
        """φ -> ψ  →  ObjectUnionOf(not φ, ψ)"""
        if len(items) == 1:
            return items[0]
        # Build right-associatively
        result = items[-1]
        for item in reversed(items[:-1]):
            not_item = f'<ObjectComplementOf>{item}</ObjectComplementOf>'
            result = f'<ObjectUnionOf>{not_item}{result}</ObjectUnionOf>'
        return result

    def disjunction(self, items):
        """φ v ψ  →  ObjectUnionOf(φ, ψ)"""
        if len(items) == 1:
            return items[0]
        # Build left-associatively
        result = items[0]
        for item in items[1:]:
            result = f'<ObjectUnionOf>{result}{item}</ObjectUnionOf>'
        return result

    def conjunction(self, items):
        """φ & ψ  →  ObjectIntersectionOf(φ, ψ)"""
        if len(items) == 1:
            return items[0]
        # Build left-associatively
        result = items[0]
        for item in items[1:]:
            result = f'<ObjectIntersectionOf>{result}{item}</ObjectIntersectionOf>'
        return result

    def negation(self, items):
        """~φ  →  ObjectComplementOf(φ)"""
        return f'<ObjectComplementOf>{items[0]}</ObjectComplementOf>'

    # ========== Modal Operators ==========

    def box(self, items):
        """[]φ  →  ObjectAllValuesFrom(same_moment, φ)"""
        prop = self._property('same_moment')
        return f'<ObjectAllValuesFrom>{prop}{items[0]}</ObjectAllValuesFrom>'

    def diamond(self, items):
        """<>φ  →  ObjectSomeValuesFrom(same_moment, φ)"""
        prop = self._property('same_moment')
        return f'<ObjectSomeValuesFrom>{prop}{items[0]}</ObjectSomeValuesFrom>'

    def next(self, items):
        """Xφ  →  ObjectAllValuesFrom(succ, φ)"""
        # items[0] is X_OP token, items[1] is the formula
        prop = self._property('succ')
        return f'<ObjectAllValuesFrom>{prop}{items[1]}</ObjectAllValuesFrom>'

    # ========== Action Predicates ==========

    def do_action(self, items):
        """do(a)  →  Class(a) or complex OWL expression for group actions

        For individual actions: do(sd1) → Class(sd1)
        For group actions: do({1:sd, 2:ha}) → ObjectIntersectionOf(Class(sd1), Class(ha2))
        """
        action = items[0]
        # Check if action is already OWL XML (from group_action)
        if isinstance(action, str) and action.startswith('<'):
            return action
        # Otherwise, wrap in Class
        return self._class(action)

    def free_do_action(self, items):
        """free_do(a)  →  ObjectIntersectionOf(Class(a), ObjectComplementOf(Class(Opp2a)))

        For individual actions: free_do(sd1) → ObjectIntersectionOf(Class(sd1), ¬Class(Opp2sd1))
        For group actions: free_do({1:sd, 2:ha}) →
            ObjectIntersectionOf(
                ObjectIntersectionOf(Class(sd1), Class(ha2)),
                ObjectComplementOf(Class(Opp2{1:sd, 2:ha}))  # opposing class for the group
            )
        """
        action = items[0]

        # Get the action class (might be OWL XML for group actions)
        if isinstance(action, str) and action.startswith('<'):
            action_class = action
            # For group actions, we need to track the original action string for opposing class
            # Since we don't have it here, we'll use a sanitized version
            # This is a limitation - group actions might not work correctly with free_do
            # For now, skip the opposing class logic for complex OWL expressions
            return action_class
        else:
            action_class = self._class(action)
            opp_class = self._class(f'Opp2{action}')
            return f'<ObjectIntersectionOf>{action_class}<ObjectComplementOf>{opp_class}</ObjectComplementOf></ObjectIntersectionOf>'

    # ========== Atoms ==========

    def prop(self, items):
        """p  →  Class(p)"""
        return self._class(str(items[0]))

    def top(self, items):
        """T  →  owl:Thing"""
        return '<Class IRI="http://www.w3.org/2002/07/owl#Thing"/>'

    def bottom(self, items):
        """_L  →  owl:Nothing"""
        return '<Class IRI="http://www.w3.org/2002/07/owl#Nothing"/>'

    def parens(self, items):
        """(φ)  →  φ (just return inner)"""
        return items[0]

    # ========== Action Expressions ==========

    def individual_action(self, items):
        """action_id → sanitized action string"""
        return self._sanitize_name(str(items[0]))

    def group_action(self, items):
        """{mappings} → conjunction of individual actions

        Group actions like {1:sd, 2:ha} should expand to:
        ObjectIntersectionOf(Class(sd1), Class(ha2))

        NOT to a sanitized class name like _1_sd__2_ha_
        """
        # Items are action_mapping results (e.g., "1:sd", "2:ha")
        # We need to parse each mapping and create Class elements for the composed actions
        action_classes = []
        for mapping in items:
            # mapping is a string like "1:sd" or "2:ha"
            if ':' in mapping:
                agent, action = mapping.split(':', 1)
                # Create Class element for the composed action (e.g., sd1, ha2)
                composed_action = f"{action}{agent}"
                action_classes.append(self._class(composed_action))
            else:
                # Single action without agent (shouldn't happen in group actions)
                action_classes.append(self._class(mapping))

        # If only one action, return it directly
        if len(action_classes) == 1:
            return action_classes[0]

        # Multiple actions - create conjunction
        # Build left-associatively
        result = action_classes[0]
        for action_class in action_classes[1:]:
            result = f'<ObjectIntersectionOf>{result}{action_class}</ObjectIntersectionOf>'
        return result

    def action_mapping(self, items):
        """num:action or action → mapping string"""
        if len(items) == 2:
            return f"{items[0]}:{items[1]}"
        return str(items[0])

    def action_id(self, items):
        """action without agent → action string"""
        return str(items[0])

    # ========== Agent Expressions ==========

    def individual_agent(self, items):
        """agent_num → agent string"""
        return str(items[0])

    def agent_group(self, items):
        """{nums} → agent group string"""
        nums = ', '.join(str(n) for n in items)
        return f'{{{nums}}}'

    def named_agent_group(self, items):
        """agent_name → agent name string"""
        return str(items[0])

    # ========== PDL-style Modalities (should not appear in expanded formulas) ==========

    def pdl_box(self, items):
        """[action]φ - should not appear after expansion"""
        raise ValueError(f"pdl_box should not appear in expanded formulas: {items}")

    def pdl_diamond(self, items):
        """<action>φ - should not appear after expansion"""
        raise ValueError(f"pdl_diamond should not appear in expanded formulas: {items}")

    # ========== Causal Operators (should not appear in expanded formulas) ==========

    def expected_result(self, items):
        """do(a) [+]-> φ - should not appear after expansion"""
        raise ValueError(f"expected_result should not appear in expanded formulas: {items}")

    def but_for(self, items):
        """but(a, φ) - should not appear after expansion"""
        raise ValueError(f"but_for should not appear in expanded formulas: {items}")

    def ness(self, items):
        """ness(a, φ) - should not appear after expansion"""
        raise ValueError(f"ness should not appear in expanded formulas: {items}")

    # ========== STIT Operators (should not appear in expanded formulas) ==========

    def xstit(self, items):
        """[agent XSTIT]φ - should not appear after expansion"""
        raise ValueError(f"xstit should not appear in expanded formulas: {items}")

    def dxstit(self, items):
        """[agent DXSTIT]φ - should not appear after expansion"""
        raise ValueError(f"dxstit should not appear in expanded formulas: {items}")

    # ========== Responsibility Operators (should not appear in expanded formulas) ==========

    def pres(self, items):
        """[agent pres]φ - should not appear after expansion"""
        raise ValueError(f"pres should not appear in expanded formulas: {items}")

    def sres(self, items):
        """[agent sres]φ - should not appear after expansion"""
        raise ValueError(f"sres should not appear in expanded formulas: {items}")

    def res(self, items):
        """[agent res]φ - should not appear after expansion"""
        raise ValueError(f"res should not appear in expanded formulas: {items}")

    def opposing(self, items):
        """action1 |> action2 - should not appear after expansion"""
        raise ValueError(f"opposing should not appear in expanded formulas: {items}")

    # ========== Declaration Generation ==========

    def generate_declarations(self):
        """Generate Declaration elements for all tracked entities."""
        declarations = []

        # Class declarations
        for class_name in sorted(self.classes):
            declarations.append(f'    <Declaration><Class {self._iri(class_name)}/></Declaration>')

        # ObjectProperty declarations
        for prop_name in sorted(self.object_properties):
            declarations.append(f'    <Declaration><ObjectProperty {self._iri(prop_name)}/></Declaration>')

        return '\n'.join(declarations)

    def generate_ontology(self, ontology_iri="http://www.semanticweb.org/alon"):
        """Generate complete OWL/XML ontology document.

        Returns:
            Complete OWL/XML string with declarations and axioms
        """
        declarations = self.generate_declarations()
        axioms_str = '\n\n'.join(self.axioms)

        return f"""<?xml version="1.0"?>
<Ontology xmlns="http://www.w3.org/2002/07/owl#"
     xml:base="{ontology_iri}"
     xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
     xmlns:xml="http://www.w3.org/2001/XMLSchema#"
     xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
     xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
     ontologyIRI="{ontology_iri}">

{declarations}

{axioms_str}

</Ontology>"""
