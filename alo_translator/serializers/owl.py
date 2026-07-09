"""
OWL serialization for ALOn models.

Two classes:

  FormulaToOWL  — Lark Transformer that converts expanded ALOn formula axioms
                  (in `name => formula` syntax) into OWL/XML SubClassOf strings.
                  Used internally by OWLSerializer to build the TBox.

  OWLSerializerBase — Abstract base providing OWL infrastructure:
                  serialize(), _build_ontology(), XML helpers, strategy support.
                  Extension points (_add_declarations, _add_succ_assertions, etc.)
                  are abstract so subclasses must implement them.

  OWLSerializer — Concrete serializer for ALOModel.  Implements all extension
                  points using HistoryPath / MomentNode structure, and uses
                  FormulaToOWL + ExpanderTransformer for the TBox.
"""

import re
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set, Tuple
from xml.etree.ElementTree import Element, SubElement, tostring, fromstring
from xml.dom import minidom
from pathlib import Path

from lark import Lark, Transformer

from .base import Serializer
from ..model.core import ALOModel, GroupAction, OpposingRelation


# ---------------------------------------------------------------------------
# FormulaToOWL — formula-level Lark transformer (TBox helper)
# ---------------------------------------------------------------------------

class FormulaToOWL(Transformer):
    """Converts expanded ALOn formula axioms to OWL/XML SubClassOf strings.

    Input:  axioms in `formula => name` syntax produced by ExpanderTransformer
    Output: OWL/XML strings accumulated in self.axioms / self.annotations
    """

    def __init__(self, base_iri="http://www.semanticweb.org/alon#", name_to_formula=None):
        self.base_iri = base_iri
        self.classes = set()
        self.object_properties = set()
        self.axioms = []
        self.annotations = []
        self.name_to_formula = name_to_formula or {}

    def _sanitize_name(self, name):
        result = str(name)
        for ch in '{}:, ()~&v|><-[]':
            result = result.replace(ch, '_')
        return result

    def _iri(self, name):
        return f'IRI="{self.base_iri}{name}"'

    def _class(self, name):
        sanitized = self._sanitize_name(name)
        self.classes.add(sanitized)
        return f'<Class {self._iri(sanitized)}/>'

    def _property(self, name):
        self.object_properties.add(name)
        return f'<ObjectProperty {self._iri(name)}/>'

    def _escape_xml(self, text):
        for old, new in [('&','&amp;'),('<','&lt;'),('>','&gt;'),('"','&quot;'),("'","&apos;")]:
            text = str(text).replace(old, new)
        return text

    # ---- top-level axiom ----

    def expansion_axiom(self, items):
        formula_owl, name = items
        name_str = str(name)
        sanitized = self._sanitize_name(name_str)
        self.classes.add(sanitized)
        axiom = f'    <SubClassOf>\n        {formula_owl}\n        <Class {self._iri(sanitized)}/>\n    </SubClassOf>'
        self.axioms.append(axiom)
        if name_str in self.name_to_formula:
            escaped = self._escape_xml(self.name_to_formula[name_str])
            self.annotations.append(
                f'    <AnnotationAssertion>\n'
                f'        <AnnotationProperty IRI="http://www.w3.org/2000/01/rdf-schema#label"/>\n'
                f'        <IRI>{self.base_iri}{name_str}</IRI>\n'
                f'        <Literal datatypeIRI="http://www.w3.org/2001/XMLSchema#string">{escaped}</Literal>\n'
                f'    </AnnotationAssertion>'
            )
        return axiom

    # ---- propositional ----

    def biconditional(self, items):
        if len(items) == 1:
            return items[0]
        result = items[-1]
        for item in reversed(items[:-1]):
            not_left = f'<ObjectComplementOf>{item}</ObjectComplementOf>'
            not_right = f'<ObjectComplementOf>{result}</ObjectComplementOf>'
            result = (f'<ObjectIntersectionOf>'
                      f'<ObjectUnionOf>{not_left}{result}</ObjectUnionOf>'
                      f'<ObjectUnionOf>{not_right}{item}</ObjectUnionOf>'
                      f'</ObjectIntersectionOf>')
        return result

    def implication(self, items):
        if len(items) == 1:
            return items[0]
        result = items[-1]
        for item in reversed(items[:-1]):
            result = f'<ObjectUnionOf><ObjectComplementOf>{item}</ObjectComplementOf>{result}</ObjectUnionOf>'
        return result

    def disjunction(self, items):
        if len(items) == 1:
            return items[0]
        result = items[0]
        for item in items[1:]:
            result = f'<ObjectUnionOf>{result}{item}</ObjectUnionOf>'
        return result

    def conjunction(self, items):
        if len(items) == 1:
            return items[0]
        result = items[0]
        for item in items[1:]:
            result = f'<ObjectIntersectionOf>{result}{item}</ObjectIntersectionOf>'
        return result

    def negation(self, items):
        return f'<ObjectComplementOf>{items[0]}</ObjectComplementOf>'

    # ---- modal ----

    def box(self, items):
        return f'<ObjectAllValuesFrom>{self._property("same_moment")}{items[0]}</ObjectAllValuesFrom>'

    def diamond(self, items):
        return f'<ObjectSomeValuesFrom>{self._property("same_moment")}{items[0]}</ObjectSomeValuesFrom>'

    def next(self, items):
        return f'<ObjectAllValuesFrom>{self._property("succ")}{items[1]}</ObjectAllValuesFrom>'

    # ---- action predicates ----

    def _free_do_individual(self, action_name):
        return (f'<ObjectIntersectionOf>{self._class(action_name)}'
                f'<ObjectComplementOf>{self._class(f"Opp2{action_name}")}</ObjectComplementOf>'
                f'</ObjectIntersectionOf>')

    def _intersect(self, exprs):
        if len(exprs) == 1:
            return exprs[0]
        result = exprs[0]
        for e in exprs[1:]:
            result = f'<ObjectIntersectionOf>{result}{e}</ObjectIntersectionOf>'
        return result

    def do_action(self, items):
        action = items[0]
        if isinstance(action, list):
            return self._intersect([self._class(a) for a in action])
        return self._class(action)

    def free_do_action(self, items):
        action = items[0]
        if isinstance(action, list):
            return self._intersect([self._free_do_individual(a) for a in action])
        return self._free_do_individual(action)

    # ---- atoms ----

    def prop(self, items):
        return self._class(str(items[0]))

    def top(self, items):
        return '<Class IRI="http://www.w3.org/2002/07/owl#Thing"/>'

    def bottom(self, items):
        return '<Class IRI="http://www.w3.org/2002/07/owl#Nothing"/>'

    def parens(self, items):
        return items[0]

    # ---- action/agent expressions ----

    def individual_action(self, items):
        return self._sanitize_name(str(items[0]))

    def group_action(self, items):
        composed = []
        for mapping in items:
            if ':' in mapping:
                agent, action = mapping.split(':', 1)
                composed.append(f"{action}{agent}")
            else:
                composed.append(mapping)
        return composed

    def action_mapping(self, items):
        return f"{items[0]}:{items[1]}" if len(items) == 2 else str(items[0])

    def action_id(self, items):
        return str(items[0])

    def individual_agent(self, items):
        return str(items[0])

    def agent_group(self, items):
        return '{' + ', '.join(str(n) for n in items) + '}'

    def named_agent_group(self, items):
        return str(items[0])

    # ---- operators that must not appear after expansion ----

    def _must_not_appear(self, name, items):
        raise ValueError(f"{name} should not appear in expanded formulas: {items}")

    def pdl_box(self, items):       self._must_not_appear("pdl_box", items)
    def pdl_diamond(self, items):   self._must_not_appear("pdl_diamond", items)
    def expected_result(self, items): self._must_not_appear("expected_result", items)
    def but_for(self, items):       self._must_not_appear("but_for", items)
    def ness(self, items):          self._must_not_appear("ness", items)
    def xstit(self, items):         self._must_not_appear("xstit", items)
    def dxstit(self, items):        self._must_not_appear("dxstit", items)
    def pres(self, items):          self._must_not_appear("pres", items)
    def sres(self, items):          self._must_not_appear("sres", items)
    def res(self, items):           self._must_not_appear("res", items)
    def opposing(self, items):      self._must_not_appear("opposing", items)


# ---------------------------------------------------------------------------
# OWLSerializerBase — abstract infrastructure
# ---------------------------------------------------------------------------

class OWLSerializerBase(Serializer):
    """Abstract base for OWL/XML serializers.

    Provides:
      - serialize() / _build_ontology() — top-level template method
      - XML helpers: _iri, _declare_class, _declare_object_property, _declare_individual
      - _index_name, _add_indices, _add_all_different
      - _add_succ_structural_axioms, _add_opposing_axioms, _opp_class_for
      - _do_prop_action, _is_complex_prop, _prop_str_to_owl_elem

    Subclasses must implement the extension points marked @abstractmethod.
    """

    BASE_IRI  = "http://www.semanticweb.org/alon#"
    OWL_NS    = "http://www.w3.org/2002/07/owl#"
    RDF_NS    = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    RDFS_NS   = "http://www.w3.org/2000/01/rdf-schema#"

    def __init__(self, model: ALOModel,
                 strategy=None,
                 evaluation_history: str = "h1"):
        super().__init__(model)
        self.evaluation_history = evaluation_history
        if strategy is None:
            from .index_strategies import EquivChainedNominalStrategy
            strategy = EquivChainedNominalStrategy()
        self.strategy = strategy
        self.query_counter = 0
        self._declared_classes: Set[str] = set()

    # ---- top-level ----

    def serialize(self) -> str:
        ontology = self._build_ontology()
        rough = tostring(ontology, encoding='unicode')
        reparsed = minidom.parseString(rough)
        xml_string = reparsed.toprettyxml(indent="    ")
        xml_string = re.sub(r'xmlns:ns0="[^"]*"\s*', '', xml_string)
        xml_string = re.sub(r'ns0:', '', xml_string)
        return xml_string

    def _build_ontology(self) -> Element:
        ontology = Element("Ontology", xmlns=self.OWL_NS, attrib={
            f"{{{self.OWL_NS}}}ontologyIRI": self.BASE_IRI,
            f"{{{self.RDF_NS}}}about": self.BASE_IRI,
        })
        self._add_declarations(ontology)
        self.strategy.add_declarations(ontology, self)
        self.strategy.add_structural_axioms(ontology, self)
        self._add_succ_structural_axioms(ontology)
        self._add_opposing_axioms(ontology)
        self._add_action_disjointness(ontology)
        self._add_indices(ontology)
        self._add_all_different(ontology)
        self.strategy.add_same_moment_structure(ontology, self)
        self._add_succ_assertions(ontology)
        self._add_action_assertions(ontology)
        self._add_proposition_assertions(ontology)
        self._add_query_classes(ontology)
        self._add_expansion_axioms(ontology)
        return ontology

    # ---- XML helpers ----

    def _iri(self, name: str) -> str:
        return f"{self.BASE_IRI}{name}"

    def _declare_class(self, ontology: Element, class_name: str, label: str = None):
        if class_name in self._declared_classes:
            return
        self._declared_classes.add(class_name)
        SubElement(SubElement(ontology, "Declaration"), "Class", {"IRI": self._iri(class_name)})
        if label:
            ann = SubElement(ontology, "AnnotationAssertion")
            SubElement(ann, "AnnotationProperty", {"IRI": f"{self.RDFS_NS}label"})
            SubElement(ann, "IRI", text=self._iri(class_name))
            SubElement(ann, "Literal", text=label)

    def _declare_object_property(self, ontology: Element, prop_name: str):
        SubElement(SubElement(ontology, "Declaration"), "ObjectProperty", {"IRI": self._iri(prop_name)})

    def _declare_individual(self, ontology: Element, ind_name: str):
        SubElement(SubElement(ontology, "Declaration"), "NamedIndividual", {"IRI": self._iri(ind_name)})

    def _index_name(self, moment: str, history: str) -> str:
        return f"{moment}_{history}"

    def _add_indices(self, ontology: Element):
        for moment, history in self._get_all_indices():
            self._declare_individual(ontology, self._index_name(moment, history))

    def _add_all_different(self, ontology: Element):
        all_indices = [self._index_name(m, h) for m, h in self._get_all_indices()]
        if len(all_indices) > 1:
            elem = SubElement(ontology, "DifferentIndividuals")
            for idx in all_indices:
                SubElement(elem, "NamedIndividual", {"IRI": self._iri(idx)})

    def _add_succ_structural_axioms(self, ontology: Element):
        SubElement(SubElement(ontology, "FunctionalObjectProperty"),
                   "ObjectProperty", {"IRI": self._iri("succ")})
        serial = SubElement(ontology, "SubClassOf")
        SubElement(serial, "Class", {"IRI": f"{self.OWL_NS}Thing"})
        some = SubElement(serial, "ObjectSomeValuesFrom")
        SubElement(some, "ObjectProperty", {"IRI": self._iri("succ")})
        SubElement(some, "Class", {"IRI": f"{self.OWL_NS}Thing"})

    def _opp_class_for(self, opposed_action) -> str:
        if isinstance(opposed_action, GroupAction):
            return opposed_action.opp_class_name()
        return f"Opp2{opposed_action}"

    def _add_opposing_axioms(self, ontology: Element):
        opposing_map: Dict[str, List] = {}
        for opp in self.model.opposings:
            opposing_map.setdefault(self._opp_class_for(opp.opposed_action), []).append(opp.opposing_action)
        for opp_class, actions in opposing_map.items():
            for action in actions:
                sub = SubElement(ontology, "SubClassOf")
                SubElement(sub, "Class", {"IRI": self._iri(str(action))})
                SubElement(sub, "Class", {"IRI": self._iri(opp_class)})

    def _do_prop_action(self, prop: str) -> Optional[str]:
        m = re.match(r'^do\((.+)\)$', prop.strip())
        return m.group(1) if m else None

    def _is_complex_prop(self, prop: str) -> bool:
        if self._do_prop_action(prop) is not None:
            return False
        return not re.match(r'^\w+$', prop.strip())

    def _prop_str_to_owl_elem(self, prop: str) -> Element:
        action_name = self._do_prop_action(prop)
        if action_name:
            elem = Element("Class")
            elem.set("IRI", self._iri(action_name))
            return elem
        if not self._is_complex_prop(prop):
            elem = Element("Class")
            elem.set("IRI", self._iri(prop.strip()))
            return elem
        # Complex formula — parse via FormulaToOWL
        grammar_path = Path(__file__).parent.parent / "parsers" / "alon_grammar_clean.lark"
        with open(grammar_path) as f:
            grammar = f.read()
        parser = Lark(grammar, start='start', parser='lalr')
        owl_ser = FormulaToOWL(base_iri=self.BASE_IRI)
        owl_xml_str = owl_ser.transform(parser.parse(prop.strip()))
        root = fromstring(f'<root xmlns="{self.OWL_NS}">{owl_xml_str}</root>')
        return list(root)[0]

    # ---- abstract extension points ----

    @abstractmethod
    def _get_all_indices(self) -> List[Tuple[str, str]]: ...

    @abstractmethod
    def _add_declarations(self, ontology: Element): ...

    @abstractmethod
    def _add_action_disjointness(self, ontology: Element): ...

    @abstractmethod
    def _add_succ_assertions(self, ontology: Element): ...

    @abstractmethod
    def _add_action_assertions(self, ontology: Element): ...

    @abstractmethod
    def _add_proposition_assertions(self, ontology: Element): ...

    @abstractmethod
    def _add_query_classes(self, ontology: Element): ...

    @abstractmethod
    def _add_expansion_axioms(self, ontology: Element): ...


# ---------------------------------------------------------------------------
# OWLSerializer — concrete implementation for ALOModel
# ---------------------------------------------------------------------------

class OWLSerializer(OWLSerializerBase):
    """OWL serializer for ALOModel (arbitrary temporal depth).

    ABox: derived from HistoryPath / MomentNode structure.
    TBox: ExpanderTransformer expands ALOn formulas; FormulaToOWL converts to OWL/XML.
    """

    def __init__(self, model: ALOModel,
                 evaluation_moment: str,
                 evaluation_history: str,
                 strategy=None):
        self.evaluation_moment = evaluation_moment
        super().__init__(model, strategy=strategy, evaluation_history=evaluation_history)

        grammar_path = Path(__file__).parent.parent / "parsers" / "alon_grammar_clean.lark"
        with open(grammar_path) as f:
            grammar = f.read()
        self.parser = Lark(grammar, start='start', parser='lalr')

        self.formula_to_owl: Optional[FormulaToOWL] = None
        self.expander = None
        self.query_name_map: Dict[str, str] = {}
        self.query_expansions: Dict[str, str] = {}

    # ---- index enumeration ----

    def _get_all_indices(self) -> List[Tuple[str, str]]:
        seen: Set[Tuple[str, str]] = set()
        indices = []
        for hist_name in sorted(self.model.histories.keys()):
            for moment_name in self.model.histories[hist_name].path:
                key = (moment_name, hist_name)
                if key not in seen:
                    seen.add(key)
                    indices.append(key)
        return indices

    def _build_cga_mappings(self):
        pass  # not needed — ALOModel uses explicit HistoryPath objects

    # ---- declarations ----

    def _add_declarations(self, ontology: Element):
        self._declare_object_property(ontology, "same_moment")
        self._declare_object_property(ontology, "succ")

        for action_type, agent_id in sorted(self._all_action_pairs()):
            action_name = f"{action_type}{agent_id}"
            self._declare_class(ontology, action_name, f"Action {action_name}")

        for prop in sorted(self._collect_all_propositions()):
            if self._do_prop_action(prop) is None and not self._is_complex_prop(prop):
                self._declare_class(ontology, prop, f"Proposition {prop}")

        for action_name in sorted(self._collect_do_prop_actions()):
            self._declare_class(ontology, action_name, f"Action {action_name}")
            self._declare_class(ontology, f"Opp2{action_name}", f"Opposing to {action_name}")

        for action_type, agent_id in sorted(self._all_action_pairs()):
            self._declare_class(ontology, f"Opp2{action_type}{agent_id}",
                                f"Opposing to {action_type}{agent_id}")

        for opp in self.model.opposings:
            if isinstance(opp.opposed_action, GroupAction):
                cls = opp.opposed_action.opp_class_name()
                self._declare_class(ontology, cls, f"Opposing to group {opp.opposed_action}")

        for query in self.model.queries:
            if query.query_id:
                self._declare_class(ontology, query.query_id, query.formula_string)

    # ---- action disjointness ----

    def _add_action_disjointness(self, ontology: Element):
        seen: Set[frozenset] = set()
        for node in self.model.moments.values():
            for agent, action_types in node.available_actions.items():
                if len(action_types) > 1:
                    key = frozenset(f"{a}{agent}" for a in action_types)
                    if key in seen:
                        continue
                    seen.add(key)
                    disjoint = SubElement(ontology, "DisjointClasses")
                    for action_type in sorted(action_types):
                        SubElement(disjoint, "Class", {"IRI": self._iri(f"{action_type}{agent}")})

    # ---- succ assertions ----

    def _add_succ_assertions(self, ontology: Element):
        seen: Set[Tuple[str, str, str]] = set()
        for hist_name in sorted(self.model.histories.keys()):
            hp = self.model.histories[hist_name]
            for i in range(len(hp.path) - 1):
                key = (hp.path[i], hist_name, hp.path[i + 1])
                if key in seen:
                    continue
                seen.add(key)
                assertion = SubElement(ontology, "ObjectPropertyAssertion")
                SubElement(assertion, "ObjectProperty", {"IRI": self._iri("succ")})
                SubElement(assertion, "NamedIndividual",
                           {"IRI": self._iri(self._index_name(hp.path[i], hist_name))})
                SubElement(assertion, "NamedIndividual",
                           {"IRI": self._iri(self._index_name(hp.path[i + 1], hist_name))})

    # ---- action assertions ----

    def _add_action_assertions(self, ontology: Element):
        for hist_name in sorted(self.model.histories.keys()):
            hp = self.model.histories[hist_name]
            for moment_name, actions_dict in hp.actions_at.items():
                idx = self._index_name(moment_name, hist_name)
                for agent, action_type in sorted(actions_dict.items()):
                    assertion = SubElement(ontology, "ClassAssertion")
                    SubElement(assertion, "Class", {"IRI": self._iri(f"{action_type}{agent}")})
                    SubElement(assertion, "NamedIndividual", {"IRI": self._iri(idx)})
                self._add_opposing_cwa(ontology, idx, moment_name)

    def _add_opposing_cwa(self, ontology: Element, idx: str, moment_name: str):
        """Closed-world negative assertions for Opp2X at this index."""
        same_moment_actions: Set[str] = set()
        for hp in self.model.histories.values():
            if moment_name in hp.path and moment_name in hp.actions_at:
                for agent, action_type in hp.actions_at[moment_name].items():
                    same_moment_actions.add(f"{action_type}{agent}")

        opp_class_members: Dict[str, Set[str]] = {}
        for opp in self.model.opposings:
            opp_class_members.setdefault(self._opp_class_for(opp.opposed_action), set()).add(str(opp.opposing_action))
        for action_type, agent_id in self._all_action_pairs():
            opp_class_members.setdefault(f"Opp2{action_type}{agent_id}", set())
        for action_name in self._collect_do_prop_actions():
            opp_class_members.setdefault(f"Opp2{action_name}", set())

        for opp_class, members in sorted(opp_class_members.items()):
            if not (same_moment_actions & members):
                neg = SubElement(ontology, "ClassAssertion")
                compl = SubElement(neg, "ObjectComplementOf")
                SubElement(compl, "Class", {"IRI": self._iri(opp_class)})
                SubElement(neg, "NamedIndividual", {"IRI": self._iri(idx)})

    # ---- proposition assertions ----

    def _add_proposition_assertions(self, ontology: Element):
        for node_name, node in self.model.moments.items():
            for hist_name in sorted(self.model.histories_through(node_name)):
                idx = self._index_name(node_name, hist_name)
                for prop in sorted(node.propositions):
                    assertion = SubElement(ontology, "ClassAssertion")
                    assertion.append(self._prop_str_to_owl_elem(prop))
                    SubElement(assertion, "NamedIndividual", {"IRI": self._iri(idx)})

    # ---- TBox: query class expansion ----

    def _make_expander(self):
        from ..parsers.expander_transformer import ExpanderTransformer
        return ExpanderTransformer(self.parser, self.model,
                                   evaluation_moment=self.evaluation_moment)

    def _add_query_classes(self, ontology: Element):
        self.expander = self._make_expander()

        for query in self.model.queries:
            query_id = query.query_id
            if not query_id:
                self.query_counter += 1
                query_id = f"q{self.query_counter:02d}"
            self.query_name_map[query.formula_string] = query_id
            self._declare_class(ontology, query_id, query.formula_string)
            try:
                result_name = self.expander.transform(self.parser.parse(query.formula_string))
                self.query_expansions[query_id] = result_name
            except Exception as e:
                raise RuntimeError(f"Failed to expand query '{query_id}' ('{query.formula_string}'): {e}") from e

        self.formula_to_owl = FormulaToOWL(
            base_iri=self.BASE_IRI,
            name_to_formula=self.expander.name_to_formula
        )

        for axiom in self.expander.axioms:
            if '=>' in axiom:
                parts = axiom.split('=>')
                if len(parts) == 2:
                    lhs, rhs = parts[0].strip(), parts[1].strip()
                    if not lhs or not rhs or lhs == rhs or lhs == '()':
                        continue
            self.formula_to_owl.transform(self.parser.parse(axiom))

        for axiom_str in self.formula_to_owl.axioms:
            m = re.search(r'<SubClassOf>\s*(.*?)\s*</SubClassOf>', axiom_str, re.DOTALL)
            if not m:
                raise RuntimeError(f"Could not extract SubClassOf content from axiom: {axiom_str[:200]}")
            ontology.append(fromstring(
                f'<SubClassOf xmlns="{self.OWL_NS}">{m.group(1).strip()}</SubClassOf>'))

        for annotation_str in self.formula_to_owl.annotations:
            m = re.search(r'<AnnotationAssertion>\s*(.*?)\s*</AnnotationAssertion>',
                          annotation_str, re.DOTALL)
            if not m:
                raise RuntimeError(f"Could not extract AnnotationAssertion content: {annotation_str[:200]}")
            ontology.append(fromstring(
                f'<AnnotationAssertion xmlns="{self.OWL_NS}" xmlns:rdfs="{self.RDFS_NS}">'
                f'{m.group(1).strip()}</AnnotationAssertion>'))

        for query_id, expansion_name in self.query_expansions.items():
            try:
                expansion_owl = self.formula_to_owl.transform(self.parser.parse(expansion_name))
                ontology.append(fromstring(
                    f'<SubClassOf xmlns="{self.OWL_NS}">\n'
                    f'        {expansion_owl}\n'
                    f'        <Class IRI="{self.BASE_IRI}{query_id}"/>\n'
                    f'    </SubClassOf>'))
            except Exception as e:
                raise RuntimeError(f"Failed to create query definition for '{query_id}': {e}") from e

    def _add_expansion_axioms(self, ontology: Element):
        all_action_names = {f"{a}{ag}" for a, ag in self._all_action_pairs()}
        all_prop_names = self._collect_all_propositions()
        for class_name in self.formula_to_owl.classes:
            if class_name in {q.query_id for q in self.model.queries if q.query_id}:
                continue
            if not (class_name in all_action_names or
                    class_name.startswith("Opp2") or
                    class_name in all_prop_names):
                self._declare_class(ontology, class_name, f"Formula {class_name}")

    # ---- private helpers ----

    def _all_action_pairs(self) -> Set[Tuple[str, str]]:
        pairs: Set[Tuple[str, str]] = set()
        for node in self.model.moments.values():
            for agent, action_types in node.available_actions.items():
                for action_type in action_types:
                    pairs.add((action_type, agent))
        return pairs

    def _collect_all_propositions(self) -> Set[str]:
        props: Set[str] = set()
        for node in self.model.moments.values():
            props.update(p for p in node.propositions if not p.startswith('~'))
        return props

    def _collect_do_prop_actions(self) -> Set[str]:
        actions: Set[str] = set()
        for node in self.model.moments.values():
            for prop in node.propositions:
                a = self._do_prop_action(prop)
                if a:
                    actions.add(a)
        return actions
