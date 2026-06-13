"""
OWL serializer for ALOModel (arbitrary temporal depth).

Inherits ABox infrastructure from OWLIndexSerializer and adds:
- ALOModel-aware index enumeration (HistoryPath.path)
- ExpanderTransformer-based TBox (query class definitions)
- evaluation_moment injection for responsibility operators
"""

import re
from typing import Dict, List, Set, Tuple
from xml.etree.ElementTree import Element, SubElement, fromstring
from lark import Lark
from pathlib import Path

from .owl_index import OWLIndexSerializer
from ..model.core import ALOModel, GroupAction
from ..parsers.expander_transformer import ExpanderTransformer
from ..serializers.owl_serializer import OwlSerializer


class OWLSerializer(OWLIndexSerializer):
    """OWL serializer for ALOModel (arbitrary temporal depth).

    ABox: derives individuals, succ chains, same_moment groups, action
    assertions, and proposition assertions directly from the ALOModel
    structure (HistoryPath.path, MomentNode.propositions, etc.).

    TBox: uses ExpanderTransformer + OwlSerializer to expand ALOn formulas
    into OWL SubClassOf axioms, with evaluation_moment injected so
    responsibility operators resolve against the correct action profile.
    """

    def __init__(self, model: ALOModel,
                 evaluation_moment: str,
                 evaluation_history: str,
                 strategy=None):
        self.evaluation_moment = evaluation_moment
        self.evaluation_history = evaluation_history
        super().__init__(model, strategy=strategy)

        grammar_path = Path(__file__).parent.parent / "parsers" / "alon_grammar_clean.lark"
        with open(grammar_path) as f:
            grammar = f.read()
        self.parser = Lark(grammar, start='start', parser='lalr')

        self.owl_serializer = None
        self.expander = None
        self.query_name_map: Dict[str, str] = {}
        self.query_expansions: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Index enumeration
    # ------------------------------------------------------------------

    def _get_all_indices(self) -> List[Tuple[str, str]]:
        """Return all (moment, history) index pairs from the ALOModel."""
        seen: Set[Tuple[str, str]] = set()
        indices: List[Tuple[str, str]] = []
        for hist_name in sorted(self.model.histories.keys()):
            hp = self.model.histories[hist_name]
            for moment_name in hp.path:
                key = (moment_name, hist_name)
                if key not in seen:
                    seen.add(key)
                    indices.append(key)
        return indices

    # ------------------------------------------------------------------
    # CGA mappings — not applicable for ALOModel
    # ------------------------------------------------------------------

    def _build_cga_mappings(self):
        """No-op: ALOModel uses explicit HistoryPath objects."""
        pass

    # ------------------------------------------------------------------
    # Declarations
    # ------------------------------------------------------------------

    def _add_declarations(self, ontology: Element):
        """Declare properties, action classes, proposition classes, and query classes."""
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
            action_name = f"{action_type}{agent_id}"
            self._declare_class(ontology, f"Opp2{action_name}", f"Opposing to {action_name}")

        for opp in self.model.opposings:
            if isinstance(opp.opposed_action, GroupAction):
                cls = opp.opposed_action.opp_class_name()
                self._declare_class(ontology, cls, f"Opposing to group {opp.opposed_action}")

        for query in self.model.queries:
            if query.query_id:
                self._declare_class(ontology, query.query_id, query.formula_string)

    # ------------------------------------------------------------------
    # Action disjointness
    # ------------------------------------------------------------------

    def _add_action_disjointness(self, ontology: Element):
        """At each moment, each agent can only choose one action."""
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
                        SubElement(disjoint, "Class",
                                   {"IRI": self._iri(f"{action_type}{agent}")})

    # ------------------------------------------------------------------
    # Succ assertions
    # ------------------------------------------------------------------

    def _add_succ_assertions(self, ontology: Element):
        """Add succ assertions for every consecutive pair in each history's path."""
        seen: Set[Tuple[str, str, str]] = set()
        for hist_name in sorted(self.model.histories.keys()):
            hp = self.model.histories[hist_name]
            for i in range(len(hp.path) - 1):
                from_mom = hp.path[i]
                to_mom = hp.path[i + 1]
                key = (from_mom, hist_name, to_mom)
                if key in seen:
                    continue
                seen.add(key)
                assertion = SubElement(ontology, "ObjectPropertyAssertion")
                SubElement(assertion, "ObjectProperty", {"IRI": self._iri("succ")})
                SubElement(assertion, "NamedIndividual",
                           {"IRI": self._iri(self._index_name(from_mom, hist_name))})
                SubElement(assertion, "NamedIndividual",
                           {"IRI": self._iri(self._index_name(to_mom, hist_name))})

    # ------------------------------------------------------------------
    # Action assertions
    # ------------------------------------------------------------------

    def _add_action_assertions(self, ontology: Element):
        """Assert action class memberships at the appropriate moment indices."""
        for hist_name in sorted(self.model.histories.keys()):
            hp = self.model.histories[hist_name]
            for moment_name, actions_dict in hp.actions_at.items():
                idx = self._index_name(moment_name, hist_name)
                for agent, action_type in sorted(actions_dict.items()):
                    action_class = f"{action_type}{agent}"
                    assertion = SubElement(ontology, "ClassAssertion")
                    SubElement(assertion, "Class", {"IRI": self._iri(action_class)})
                    SubElement(assertion, "NamedIndividual", {"IRI": self._iri(idx)})

                self._add_layered_opposing_assertions(ontology, idx, moment_name)

    def _add_layered_opposing_assertions(self, ontology: Element,
                                         idx: str, moment_name: str):
        """Add negative Opp2X assertions for indices where the opposing action is absent."""
        same_moment_actions: Set[str] = set()
        for h_name, hp in self.model.histories.items():
            if moment_name in hp.path and moment_name in hp.actions_at:
                for agent, action_type in hp.actions_at[moment_name].items():
                    same_moment_actions.add(f"{action_type}{agent}")

        opp_class_members: Dict[str, Set[str]] = {}
        for opp in self.model.opposings:
            opp_class = self._opp_class_for(opp.opposed_action)
            opp_class_members.setdefault(opp_class, set()).add(str(opp.opposing_action))

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

    # ------------------------------------------------------------------
    # Proposition assertions
    # ------------------------------------------------------------------

    def _add_proposition_assertions(self, ontology: Element):
        """Assert proposition memberships at moment indices."""
        for node_name, node in self.model.moments.items():
            for hist_name in sorted(self.model.histories_through(node_name)):
                idx = self._index_name(node_name, hist_name)
                for prop in sorted(node.propositions):
                    assertion = SubElement(ontology, "ClassAssertion")
                    assertion.append(self._prop_str_to_owl_elem(prop))
                    SubElement(assertion, "NamedIndividual", {"IRI": self._iri(idx)})

    # ------------------------------------------------------------------
    # TBox: query class expansion
    # ------------------------------------------------------------------

    def _make_expander(self) -> ExpanderTransformer:
        """Return an ExpanderTransformer configured for the evaluation moment."""
        return ExpanderTransformer(self.parser, self.model,
                                   evaluation_moment=self.evaluation_moment)

    def _add_query_classes(self, ontology: Element):
        """Expand each query formula and add SubClassOf axioms to the ontology."""
        self.expander = self._make_expander()

        for query in self.model.queries:
            query_id = query.query_id
            if not query_id:
                self.query_counter += 1
                query_id = f"q{self.query_counter:02d}"

            self.query_name_map[query.formula_string] = query_id
            self._declare_class(ontology, query_id, query.formula_string)

            try:
                tree = self.parser.parse(query.formula_string)
                result_name = self.expander.transform(tree)
                self.query_expansions[query_id] = result_name
            except Exception as e:
                print(f"Warning: Could not expand query '{query_id}': {e}")
                annotation = SubElement(ontology, "AnnotationAssertion")
                SubElement(annotation, "AnnotationProperty",
                          {"IRI": f"{self.RDFS_NS}comment"})
                SubElement(annotation, "IRI", text=self._iri(query_id))
                SubElement(annotation, "Literal", text=f"Expansion failed: {str(e)}")

        self.owl_serializer = OwlSerializer(
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
            axiom_tree = self.parser.parse(axiom)
            self.owl_serializer.transform(axiom_tree)

        for axiom_str in self.owl_serializer.axioms:
            try:
                match = re.search(r'<SubClassOf>\s*(.*?)\s*</SubClassOf>', axiom_str, re.DOTALL)
                if match:
                    wrapped = f'<SubClassOf xmlns="{self.OWL_NS}">{match.group(1).strip()}</SubClassOf>'
                    ontology.append(fromstring(wrapped))
                else:
                    print(f"Warning: Could not extract SubClassOf content: {axiom_str[:200]}")
            except Exception as e:
                print(f"Warning: Could not parse axiom XML: {e}\nAxiom: {axiom_str[:200]}")

        for annotation_str in self.owl_serializer.annotations:
            try:
                match = re.search(r'<AnnotationAssertion>\s*(.*?)\s*</AnnotationAssertion>',
                                  annotation_str, re.DOTALL)
                if match:
                    wrapped = (f'<AnnotationAssertion xmlns="{self.OWL_NS}" '
                               f'xmlns:rdfs="{self.RDFS_NS}">{match.group(1).strip()}</AnnotationAssertion>')
                    ontology.append(fromstring(wrapped))
            except Exception as e:
                print(f"Warning: Could not parse annotation XML: {e}")

        for query_id, expansion_name in self.query_expansions.items():
            try:
                expansion_tree = self.parser.parse(expansion_name)
                expansion_owl = self.owl_serializer.transform(expansion_tree)
                wrapped = (f'<SubClassOf xmlns="{self.OWL_NS}">\n'
                           f'        {expansion_owl}\n'
                           f'        <Class IRI="{self.BASE_IRI}{query_id}"/>\n'
                           f'    </SubClassOf>')
                ontology.append(fromstring(wrapped))
            except Exception as e:
                print(f"Warning: Could not create query definition for {query_id}: {e}")

    def _add_expansion_axioms(self, ontology: Element):
        """Declare intermediate formula classes generated by the expander."""
        all_action_names = {f"{a}{ag}" for a, ag in self._all_action_pairs()}
        all_prop_names = self._collect_all_propositions()

        for class_name in self.owl_serializer.classes:
            if class_name in {q.query_id for q in self.model.queries if q.query_id}:
                continue
            is_action = class_name in all_action_names
            is_opposing = class_name.startswith("Opp2")
            is_prop = class_name in all_prop_names
            if not (is_action or is_opposing or is_prop):
                self._declare_class(ontology, class_name, f"Formula {class_name}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _all_action_pairs(self) -> Set[Tuple[str, str]]:
        """Return all (action_type, agent_id) pairs across all moment nodes."""
        pairs: Set[Tuple[str, str]] = set()
        for node in self.model.moments.values():
            for agent, action_types in node.available_actions.items():
                for action_type in action_types:
                    pairs.add((action_type, agent))
        return pairs

    def _collect_all_propositions(self) -> Set[str]:
        """Return all non-negated proposition strings from all moment nodes."""
        props: Set[str] = set()
        for node in self.model.moments.values():
            props.update(p for p in node.propositions if not p.startswith('~'))
        return props

    def _collect_do_prop_actions(self) -> Set[str]:
        """Return action names derived from do(X) proposition labels."""
        actions: Set[str] = set()
        for node in self.model.moments.values():
            for prop in node.propositions:
                a = self._do_prop_action(prop)
                if a:
                    actions.add(a)
        return actions
