"""Post-process a serialized OWL ontology, rewriting query-definition
SubClassOf axioms into DLSafeRule form.

Konclude parses but silently drops DL-safe rules (see
docs/owl_rules_investigation.md) -- this transform is for HermiT (via
ROBOT), which supports them natively. Operates on the OWL/XML text
OWLSerializer already produces; does not touch OWLSerializer/FormulaToOWL
itself, so it stays mechanically in sync with whatever they emit.

Translation: SubClassOf(<expr>, query_id) -> DLSafeRule(
    Body(ClassAtom(<same expr, unchanged>, Variable(:x)))
    Head(ClassAtom(query_id, Variable(:x)))
)
The LHS <expr> is transplanted unchanged (deep-copied), whatever its
shape -- bare Class or arbitrarily nested ObjectIntersectionOf/
ObjectUnionOf/ObjectComplementOf/ObjectAllValuesFrom/etc. No
negation-as-failure needed: DL-safe rule atoms accept arbitrary OWL
class expressions, including ObjectComplementOf, which is real
classical negation already baked into the expression.

Only SubClassOf axioms whose head is a real query ID (from
model.queries) are rewritten. Everything else (structural axioms like
the succ-totality axiom, opposing-relation axioms like
SubClassOf(ha2, Opp2sd1), and any axiom not about a query) is passed
through unchanged.
"""

import copy
import re
from typing import Set
from xml.etree.ElementTree import Element, fromstring, tostring
import xml.dom.minidom as minidom

OWL_NS = "http://www.w3.org/2002/07/owl#"
DEFAULT_BASE_IRI = "http://www.semanticweb.org/alon#"


def _tag(elem: Element) -> str:
    return elem.tag.split("}")[-1]


def _strip_ns_prefix(elem: Element) -> None:
    """Recursively strip the {namespace} prefix lark/ElementTree add to tags,
    matching the plain (no-namespace-prefix) tags OWLSerializer.serialize()
    already produces in its output text.
    """
    elem.tag = _tag(elem)
    for child in elem:
        _strip_ns_prefix(child)


def to_dlsafe_rules(owl_xml: str, query_ids: Set[str], base_iri: str = DEFAULT_BASE_IRI) -> str:
    """Rewrite query-definition SubClassOf axioms into DLSafeRule form.

    Args:
        owl_xml: Serialized OWL/XML string (OWLSerializer.serialize() output,
            or any OWL/XML with the same axiom shapes)
        query_ids: Set of class names to convert to DLSafeRule form. Callers
            MUST exclude any `outcome_*` query ID from this set -- see
            docs/reasoner_oddities.md: converting an `outcome_<...>` query
            (whose body is a single non-compound ObjectSomeValuesFrom/
            ObjectAllValuesFrom atom -- setup_layered_queries in
            streamlit_app/utils.py always adds exactly one per eval point)
            to a DLSafeRule breaks OTHER, unrelated rules' derivation under
            HermiT/ROBOT, confirmed via clean bisection. Root cause unknown;
            leaving outcome_* as a plain SubClassOf axiom is a verified
            workaround, not yet automated here since callers should be
            able to see this constraint rather than have it silently
            applied.

    Returns:
        Rewritten OWL/XML string with query-definition SubClassOf axioms
        replaced by equivalent DLSafeRule axioms.
    """
    root = fromstring(owl_xml)
    new_children = []
    var_x = Element("Variable", {"IRI": f"{base_iri}x"})

    for child in list(root):
        tag = _tag(child)
        if tag != "SubClassOf":
            new_children.append(child)
            continue

        kids = [c for c in child if isinstance(c.tag, str)]
        if len(kids) != 2:
            new_children.append(child)
            continue

        lhs, head = kids
        head_iri = head.get("IRI", "")
        head_name = head_iri.split("/")[-1].split("#")[-1]
        if _tag(head) != "Class" or head_name not in query_ids:
            new_children.append(child)
            continue

        rule = Element("DLSafeRule")
        body = Element("Body")
        body_atom = Element("ClassAtom")
        body_atom.append(copy.deepcopy(lhs))
        body_atom.append(copy.deepcopy(var_x))
        body.append(body_atom)
        rule.append(body)

        head_elem = Element("Head")
        head_atom = Element("ClassAtom")
        head_atom.append(copy.deepcopy(head))
        head_atom.append(copy.deepcopy(var_x))
        head_elem.append(head_atom)
        rule.append(head_elem)

        new_children.append(rule)

    root[:] = new_children

    rough = tostring(root, encoding='unicode')
    reparsed = minidom.parseString(rough)
    xml_string = reparsed.toprettyxml(indent="    ")
    xml_string = re.sub(r'xmlns:ns0="[^"]*"\s*', '', xml_string)
    xml_string = re.sub(r'ns0:', '', xml_string)
    return xml_string
