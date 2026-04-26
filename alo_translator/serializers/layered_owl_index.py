"""
OWL Index serializer for LayeredALOModel (TD>1).

Extends OWLIndexNewExpanderSerializer, overriding the ABox generation methods
to work with LayeredALOModel's multi-hop moment structure.  The TBox (formula
expansion + OwlSerializer) is inherited unchanged — ExpanderTransformer already
handles LayeredALOModel when evaluation_moment is supplied.

Same-moment strategies (EquivChainedNominalStrategy, EquivFullCardinalityStrategy,
etc.) work without modification because they delegate index enumeration to
serializer._get_all_indices(), which we override here.
"""

from typing import Dict, List, Set, Tuple, Optional
from xml.etree.ElementTree import Element, SubElement

from .owl_index_new_expander import OWLIndexNewExpanderSerializer
from ..model.core import LayeredALOModel
from ..parsers.expander_transformer import ExpanderTransformer


class LayeredOWLIndexSerializer(OWLIndexNewExpanderSerializer):
    """OWL serializer for LayeredALOModel (arbitrary temporal depth).

    ABox: derives individuals, succ chains, same_moment groups, action
    assertions, and proposition assertions directly from the LayeredALOModel
    structure (HistoryPath.path, MomentNode.propositions, etc.).

    TBox: inherited from OWLIndexNewExpanderSerializer — ExpanderTransformer
    with evaluation_moment set, fed into OwlSerializer as before.
    """

    def __init__(self, model: LayeredALOModel,
                 evaluation_moment: str,
                 evaluation_history: str,
                 strategy=None):
        # evaluation_moment / evaluation_history needed before super().__init__
        # because _add_query_classes is called during _build_ontology → serialize()
        self.evaluation_moment = evaluation_moment
        self.evaluation_history = evaluation_history

        # Temporarily set model attributes super().__init__ reads
        # (OWLIndexSerializer.__init__ only does self.model = model + bookkeeping)
        super().__init__(model, strategy=strategy)

    # ------------------------------------------------------------------
    # Index enumeration — the central override
    # ------------------------------------------------------------------

    def _get_all_indices(self) -> List[Tuple[str, str]]:
        """Return all (moment, history) index pairs from the LayeredALOModel.

        Enumerates every step in every history's path, preserving path order so
        that same-moment strategies see indices in a consistent sequence.
        """
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
    # CGA mappings — not applicable for LayeredALOModel
    # ------------------------------------------------------------------

    def _build_cga_mappings(self):
        """No-op: LayeredALOModel uses explicit HistoryPath objects."""
        pass

    # ------------------------------------------------------------------
    # Declarations
    # ------------------------------------------------------------------

    def _add_declarations(self, ontology: Element):
        """Declare properties, action classes, proposition classes, and query classes."""
        self._declare_object_property(ontology, "same_moment")
        self._declare_object_property(ontology, "succ")

        # Action classes — collect from all moment nodes
        for action_type, agent_id in sorted(self._all_action_pairs()):
            action_name = f"{action_type}{agent_id}"
            self._declare_class(ontology, action_name, f"Action {action_name}")

        # Proposition classes (non-negated, non-do())
        for prop in sorted(self._collect_all_propositions()):
            if self._do_prop_action(prop) is None:
                self._declare_class(ontology, prop, f"Proposition {prop}")

        # Virtual action classes derived from do(X) proposition labels
        for action_name in sorted(self._collect_do_prop_actions()):
            self._declare_class(ontology, action_name, f"Action {action_name}")
            self._declare_class(ontology, f"Opp2{action_name}", f"Opposing to {action_name}")

        # Opp2X classes for every action
        for action_type, agent_id in sorted(self._all_action_pairs()):
            action_name = f"{action_type}{agent_id}"
            self._declare_class(ontology, f"Opp2{action_name}", f"Opposing to {action_name}")

        # Query classes
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
    # Opposing axioms — inherited (_add_opposing_axioms uses model.opposings ✓)
    # ------------------------------------------------------------------

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

                # Closed-world negative assertions for Opp2X at this index
                self._add_layered_opposing_assertions(ontology, idx, moment_name)

    def _add_layered_opposing_assertions(self, ontology: Element,
                                         idx: str, moment_name: str):
        """Add negative Opp2X assertions for indices where the opposing action is absent.

        Checks all same-moment histories (those whose path includes moment_name)
        to determine which opposing actions are present at this moment.
        """
        # Collect actions present across ALL same-moment histories at this moment
        same_moment_actions: Set[str] = set()
        for h_name, hp in self.model.histories.items():
            if moment_name in hp.path and moment_name in hp.actions_at:
                for agent, action_type in hp.actions_at[moment_name].items():
                    same_moment_actions.add(f"{action_type}{agent}")

        # Build Opp2X → {members} map from model's opposing relations
        opp_class_members: Dict[str, Set[str]] = {}
        for opp in self.model.opposings:
            opp_class = f"Opp2{opp.opposed_action}"
            opp_class_members.setdefault(opp_class, set()).add(str(opp.opposing_action))

        # Ensure every action has an entry (even if no explicit opposing)
        for action_type, agent_id in self._all_action_pairs():
            opp_class = f"Opp2{action_type}{agent_id}"
            opp_class_members.setdefault(opp_class, set())
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
        """Assert proposition memberships at leaf moment indices (closed-world)."""
        all_props = self._collect_all_propositions()
        all_action_props = {p for p in all_props if self._do_prop_action(p) is not None}
        all_regular_props = all_props - all_action_props

        for node_name, node in self.model.moments.items():
            if not node.is_leaf:
                continue
            true_props = {p for p in node.propositions if not p.startswith('~')}
            false_regular = all_regular_props - true_props
            false_action_props = {p for p in all_action_props if p not in true_props}

            for hist_name in sorted(self.model.histories_through(node_name)):
                leaf_idx = self._index_name(node_name, hist_name)

                for prop in sorted(true_props):
                    action_name = self._do_prop_action(prop)
                    assertion = SubElement(ontology, "ClassAssertion")
                    if action_name:
                        SubElement(assertion, "Class", {"IRI": self._iri(action_name)})
                    else:
                        SubElement(assertion, "Class", {"IRI": self._iri(prop)})
                    SubElement(assertion, "NamedIndividual", {"IRI": self._iri(leaf_idx)})

                for prop in sorted(false_regular):
                    neg = SubElement(ontology, "ClassAssertion")
                    compl = SubElement(neg, "ObjectComplementOf")
                    SubElement(compl, "Class", {"IRI": self._iri(prop)})
                    SubElement(neg, "NamedIndividual", {"IRI": self._iri(leaf_idx)})

                for prop in sorted(false_action_props):
                    action_name = self._do_prop_action(prop)
                    neg = SubElement(ontology, "ClassAssertion")
                    compl = SubElement(neg, "ObjectComplementOf")
                    SubElement(compl, "Class", {"IRI": self._iri(action_name)})
                    SubElement(neg, "NamedIndividual", {"IRI": self._iri(leaf_idx)})

    # ------------------------------------------------------------------
    # Query classes — override factory to inject evaluation_moment
    # ------------------------------------------------------------------

    def _make_expander(self) -> ExpanderTransformer:
        """Return an ExpanderTransformer configured for the evaluation moment."""
        return ExpanderTransformer(self.parser, self.model,
                                   evaluation_moment=self.evaluation_moment)

    # ------------------------------------------------------------------
    # Expansion axiom declarations
    # ------------------------------------------------------------------

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
