"""
Extract model-structure translation examples by calling each structural
_add_*/_generate_* method DIRECTLY against a canonical model
(streamlit_app/models/3.1.mmd -- TD=1, 4 histories sharing one
same-moment group, one opposing relation, 2 agents; small enough to read,
exercises every structural feature), one category at a time, against a
fresh Element/output buffer each time -- not by pattern-matching a merged
document (tag names like ClassAssertion/SubClassOf are reused across
categories in the real output, which makes post-hoc regex matching
unreliable; calling the method directly is exact by construction).

Unlike extract_primitives.py, this is NOT purely static AST extraction --
these methods are multi-line loops building XML/strings from real model
data, not single expressions; there's no honest single-AST-node "the
rule" to pull out mechanically. Per explicit design decision: run the
real methods, capture their real output, let a human write the framing
prose around it afterward.

Usage:
  python -m tools.translation_table.extract_structural
"""

import sys
from pathlib import Path
from xml.etree.ElementTree import Element, tostring
from xml.dom import minidom
import re

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from alo_translator.parsers.dbt_parser import parse_dbt_diagram
from alo_translator.serializers.owl import OWLSerializer
from alo_translator.serializers.datalog import DatalogIndexSerializer

CANONICAL_MODEL = REPO_ROOT / "streamlit_app" / "models" / "3.1.mmd"


def _build_owl_serializer() -> OWLSerializer:
    model = parse_dbt_diagram(CANONICAL_MODEL.read_text())
    return OWLSerializer(model, evaluation_moment="m", evaluation_history="h1")


def _build_datalog_serializer() -> DatalogIndexSerializer:
    model = parse_dbt_diagram(CANONICAL_MODEL.read_text())
    return DatalogIndexSerializer(model, evaluation_history="h1", evaluation_moment="m")


def _pretty(ontology: Element) -> str:
    rough = tostring(ontology, encoding="unicode")
    reparsed = minidom.parseString(rough)
    xml_string = reparsed.toprettyxml(indent="    ")
    xml_string = re.sub(r'xmlns:ns0="[^"]*"\s*', '', xml_string)
    xml_string = re.sub(r'ns0:', '', xml_string)
    # Drop the wrapping <root>/<?xml?> lines -- only the children matter here.
    lines = [l for l in xml_string.splitlines() if l.strip() and '<?xml' not in l and l.strip() not in ('<root>', '</root>')]
    return "\n".join(lines)


def _owl_fragment(method_name: str, *args) -> str:
    """Call an OWLSerializer method in isolation against a fresh Element,
    return the pretty-printed XML it produced (only its own output, no
    other structural method's contribution mixed in).
    """
    serializer = _build_owl_serializer()
    root = Element("root")
    getattr(serializer, method_name)(root, *args)
    return _pretty(root)


def _datalog_fragment(method_name: str) -> str:
    serializer = _build_datalog_serializer()
    return getattr(serializer, method_name)()


# (category, owl_method, owl_extra_args, datalog_method)
STRUCTURAL_METHODS = [
    ("indices", "_add_indices", (), "_generate_structural_facts"),
    ("succ", "_add_succ_structural_axioms", (), None),  # totality axiom, no direct datalog counterpart (see notes)
    ("succ_assertions", "_add_succ_assertions", (), None),  # facts already shown under "indices" (_generate_structural_facts covers both)
    ("same_moment", None, (), "_generate_structural_rules"),  # OWL side is strategy-dependent, see notes
    ("action_disjointness", "_add_action_disjointness", (), None),
    ("action_assertions", "_add_action_assertions", (), "_generate_action_facts"),
    ("opposing", "_add_opposing_axioms", (), "_generate_opposing_rules"),
    ("propositions", "_add_proposition_assertions", (), "_generate_proposition_facts"),
]


def build_examples() -> dict:
    results = {}
    for category, owl_method, owl_args, datalog_method in STRUCTURAL_METHODS:
        owl_out = _owl_fragment(owl_method, *owl_args) if owl_method else None
        datalog_out = _datalog_fragment(datalog_method) if datalog_method else None
        results[category] = {"owl": owl_out, "datalog": datalog_out}
    return results


def main():
    examples = build_examples()
    for category, content in examples.items():
        print(f"=== {category} ===")
        print("-- OWL --")
        print(content["owl"] if content["owl"] is not None else "(no direct method / see notes)")
        print("-- Datalog --")
        print(content["datalog"] if content["datalog"] is not None else "(no direct method / see notes)")
        print()


if __name__ == "__main__":
    main()
