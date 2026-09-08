"""
Extract model-structure translation examples for the "concrete syntax"
table: for each of the 4 semantic components of an ALOn model
M = (DBT, act, nu) (per Alon4Fear/2Prelims.tex's "Semantics of ALOn"
definition) plus the action structure A=(A,n,>) the model is defined
over, show the CONCRETE .mmd syntax that denotes it, alongside the real
OWL and Datalog realization -- run against streamlit_app/models/3.1.mmd
(TD=1, 4 histories sharing one same-moment group, one opposing relation,
2 agents; small enough to read, exercises every structural feature).

The model itself has no formal grammar in the paper to be faithful to
(unlike the primitive-formula table, which mirrors the paper's own
phi ::= ... grammar exactly) -- .mmd/YAML frontmatter is this project's
own invention, not something the paper defines. So this table's row set
is grounded in the paper's SEMANTIC definition of what a model consists
of (DBT structure / act / nu / action-structure-with-opposing), not in
this codebase's internal method names -- an earlier version organized
rows around _add_succ_structural_axioms vs _add_succ_assertions vs
_add_indices etc. (this codebase's own method boundaries) and produced
an incoherent table where the same facts appeared split across multiple
rows with no clear semantic home; this version fixes that.

Each row is a genuine multi-way correspondence, not just "run this
Python method": the CONCRETE_SYNTAX snippet is pulled verbatim from the
real 3.1.mmd source (not hand-typed, so it can't silently drift from the
actual canonical model file); the OWL/Datalog fragments are captured by
calling the real serializer methods directly against a fresh output
buffer, isolated per row (same technique as before -- calling a method
in isolation is exact by construction, unlike regex-matching a merged
document).

Usage:
  python -m tools.translation_table.extract_structural
"""

import re
import sys
from pathlib import Path
from xml.etree.ElementTree import Element, tostring
from xml.dom import minidom

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from alo_translator.parsers.dbt_parser import parse_dbt_diagram
from alo_translator.serializers.owl import OWLSerializer
from alo_translator.serializers.datalog import DatalogIndexSerializer
from alo_translator.serializers.index_strategies import EquivFullCardinalityStrategy

CANONICAL_MODEL = REPO_ROOT / "streamlit_app" / "models" / "3.1.mmd"


def _build_owl_serializer() -> OWLSerializer:
    # EquivFullCardinalityStrategy explicitly, matching what
    # papers/2026Fear/generate_tables.py actually uses -- NOT
    # OWLSerializerBase's own class-level default (EquivChainedNominalStrategy),
    # which is a different strategy with different same_moment structure.
    model = parse_dbt_diagram(CANONICAL_MODEL.read_text())
    return OWLSerializer(model, evaluation_moment="m", evaluation_history="h1",
                          strategy=EquivFullCardinalityStrategy())


def _build_datalog_serializer() -> DatalogIndexSerializer:
    model = parse_dbt_diagram(CANONICAL_MODEL.read_text())
    return DatalogIndexSerializer(model, evaluation_history="h1", evaluation_moment="m")


def _pretty(ontology: Element) -> str:
    rough = tostring(ontology, encoding="unicode")
    reparsed = minidom.parseString(rough)
    xml_string = reparsed.toprettyxml(indent="    ")
    xml_string = re.sub(r'xmlns:ns0="[^"]*"\s*', '', xml_string)
    xml_string = re.sub(r'ns0:', '', xml_string)
    lines = [
        l for l in xml_string.splitlines()
        if l.strip() and '<?xml' not in l
        and not re.match(r'^</?root\b[^>]*>$', l.strip())
    ]
    return "\n".join(lines)


def _owl_fragment(method_name: str) -> str:
    serializer = _build_owl_serializer()
    root = Element("root")
    getattr(serializer, method_name)(root)
    return _pretty(root)


def _owl_same_moment_fragment() -> str:
    """same_moment structure is strategy-dependent (self.strategy.
    add_structural_axioms / add_same_moment_structure), not a plain
    serializer._add_* method -- verified against the real strategy
    generate_tables.py uses (EquivFullCardinalityStrategy)."""
    serializer = _build_owl_serializer()
    root = Element("root")
    serializer.strategy.add_structural_axioms(root, serializer)
    serializer.strategy.add_same_moment_structure(root, serializer)
    return _pretty(root)


def _datalog_fragment(method_name: str) -> str:
    serializer = _build_datalog_serializer()
    return getattr(serializer, method_name)()


def _first_n(text: str, n_lines: int) -> str:
    lines = [l for l in text.splitlines() if l.strip()]
    return "\n".join(lines[:n_lines])


# Each row: (label, math_notation, concrete_syntax_snippet,
#            owl_method(s), datalog_method(s), meaning)
# concrete_syntax_snippet is pulled verbatim from CANONICAL_MODEL below,
# not hand-retyped -- see _extract_snippet.

def _extract_snippet(pattern: str | None) -> str:
    if pattern is None:
        return "(derived from moment-grouping, not written directly)"
    text = CANONICAL_MODEL.read_text()
    m = re.search(pattern, text)
    if not m:
        raise RuntimeError(f"Pattern {pattern!r} not found in {CANONICAL_MODEL}")
    return m.group(0)


# owl_rendering/datalog_rendering: short, hand-written, table-cell-sized
# notation -- the actual published content. owl_methods/datalog_methods:
# used only to verify (via build_examples()/main() below) that the real
# serializer methods still produce output consistent with the hand-written
# rendering -- NOT rendered into the LaTeX output itself (per explicit
# instruction: no worked examples/source dumps in the published table).
# sparql_rendering: the SPARQL query path (FormulaToSPARQL, see
# docs/sparql_serializer.md) does NOT re-derive its own structural
# axioms -- it queries the SAME ABox ground facts OWL's ontology already
# asserts (OWLSerializer.serialize_structural_only(): succ/same_moment/
# action/prop assertions, unchanged from the full serialize() path, minus
# only the per-query SubClassOf expansion axioms SPARQL doesn't need --
# see that method's docstring). So every structural row's SPARQL cell is
# "the same ground fact as OWL, retrieved via a plain triple pattern",
# not a separately-derived translation -- stated honestly as such rather
# than duplicating OWL's cell content under a different heading.
ROWS = [
    {
        "label": "dbt",
        "math": r"$\mathsf{succ}(\mh) = m'$",
        "concrete_pattern": r"m --> m1 : h1\(\{sd1, ss2\}\)",
        "owl_rendering": r"$\mathsf{succ}$ a \texttt{FunctionalObjectProperty}; $\mathsf{succ}(\langle m,h\rangle, m')$ an \texttt{ObjectPropertyAssertion}",
        "sparql_rendering": r"$\mathtt{alon}{:}\langle m,h\rangle\ \mathtt{alon}{:}\mathtt{succ}\ \mathtt{alon}{:}m'\ \mathtt{.}$ (same ground fact as OWL)",
        "datalog_rendering": r"$\mathit{succ}(\langle m,h\rangle, m')$",
        "owl_methods": ["_add_succ_structural_axioms", "_add_succ_assertions", "_add_indices"],
        "datalog_methods": ["_generate_structural_facts"],
    },
    {
        "label": "act",
        "math": r"$\mathbf{act}(\mh) = \vec a$",
        "concrete_pattern": r"m --> m1 : h1\(\{sd1, ss2\}\)",
        "owl_rendering": r"$\mathsf{ClassAssertion}(a_i, \langle m,h\rangle)$ per agent $i$'s action $a_i$",
        "sparql_rendering": r"$\mathtt{alon}{:}\langle m,h\rangle\ \mathtt{a}\ \mathtt{alon}{:}a_i\ \mathtt{.}$ per agent $i$'s action $a_i$ (same ground fact as OWL)",
        "datalog_rendering": r"$\mathit{action}(\langle m,h\rangle, a_i)$ per agent",
        "owl_methods": ["_add_action_assertions", "_add_action_disjointness"],
        "datalog_methods": ["_generate_action_facts"],
    },
    {
        "label": "nu",
        "math": r"$\nu(m) \ni q$",
        "concrete_pattern": r"m1: q",
        "owl_rendering": r"$\mathsf{ClassAssertion}(q, \langle m,h\rangle)$",
        "sparql_rendering": r"$\mathtt{alon}{:}\langle m,h\rangle\ \mathtt{a}\ \mathtt{alon}{:}q\ \mathtt{.}$ (same ground fact as OWL)",
        "datalog_rendering": r"$\mathit{prop}(\langle m,h\rangle, q)$",
        "owl_methods": ["_add_proposition_assertions"],
        "datalog_methods": ["_generate_proposition_facts"],
    },
    {
        "label": "opposing",
        "math": r"$\vec a \rhd \vec b$",
        "concrete_pattern": r"opposings:\n  sd1:\n    - ha2",
        "owl_rendering": r"$\mathsf{SubClassOf}(b, \mathit{Opp2}a)$",
        "sparql_rendering": (
            r"not queried directly (\texttt{Opp2}$a$ is an OWL class only) -- reached inline via "
            r"\texttt{free\_do\_action}'s negated-\texttt{Opp2} pattern (Table 4), not as its own row here"
        ),
        "datalog_rendering": r"$\mathit{opposing}_a(I) \Leftarrow \mathit{action}(I, b)$",
        "owl_methods": ["_add_opposing_axioms"],
        "datalog_methods": ["_generate_opposing_rules"],
    },
    {
        "label": "same_moment",
        "math": r"$h,h' \in \mathcal{H}_m \Rightarrow \mh \sim \idx{m}{h'}$",
        "concrete_pattern": None,  # derived from moment-grouping, not written directly in .mmd
        "owl_rendering": (
            r"$\mathit{same\_moment}$ declared \texttt{Reflexive\-Object\-Property} and "
            r"\texttt{Symmetric\-Object\-Property}; pairwise \texttt{ObjectPropertyAssertion}s, plus "
            r"\texttt{ObjectExactCardinality}$(|\mathcal{H}_m|)$ per index"
        ),
        "sparql_rendering": (
            r"$\mathtt{alon}{:}\idx{m}{h}\ \mathtt{alon}{:}\mathtt{same\_moment}\ \mathtt{alon}{:}\idx{m}{h'}\ \mathtt{.}$ "
            r"(same pairwise ground facts as OWL; the \texttt{ReflexiveObjectProperty}/"
            r"\texttt{SymmetricObjectProperty} schema-level declarations are OWL-only bookkeeping, "
            r"not needed by SPARQL since the pairs are already materialized)"
        ),
        "datalog_rendering": r"transitive closure of $\mathit{same\_moment\_base}$",
        "owl_methods": None,  # strategy-dependent, verified separately -- see verify_against_real_output
        "datalog_methods": ["_generate_structural_rules"],
    },
]


def build_rows() -> list[dict]:
    """Rows for the published table: math notation, concrete .mmd syntax
    (verified to exist in the real canonical model, not hand-retyped),
    and the compact hand-written OWL/Datalog renderings. No code dumps.
    """
    results = []
    for row in ROWS:
        results.append({
            "label": row["label"],
            "math": row["math"],
            "concrete_syntax": _extract_snippet(row["concrete_pattern"]),
            "owl_rendering": row["owl_rendering"],
            "sparql_rendering": row["sparql_rendering"],
            "datalog_rendering": row["datalog_rendering"],
        })
    return results


def verify_against_real_output() -> None:
    """Not part of the published table -- runs the real serializer
    methods and prints their actual output, so a human can check the
    hand-written owl_rendering/datalog_rendering above still matches
    reality after a code change. Run manually:
      python -m tools.translation_table.extract_structural --verify
    """
    for row in ROWS:
        if row["owl_methods"] is None:
            owl_fragments = [_owl_same_moment_fragment()]
        else:
            owl_fragments = [_owl_fragment(m) for m in row["owl_methods"]]
        datalog_fragments = [_datalog_fragment(m) for m in row["datalog_methods"]]
        print(f"=== {row['label']} ({row['math']}) ===")
        print("hand-written OWL rendering:   ", row["owl_rendering"])
        print("hand-written Datalog rendering:", row["datalog_rendering"])
        print("-- actual OWL output (first lines) --")
        print(_first_n("\n\n".join(owl_fragments), 6))
        print("-- actual Datalog output (first lines) --")
        print(_first_n("\n\n".join(datalog_fragments), 6))
        print()


def main():
    if "--verify" in sys.argv:
        verify_against_real_output()
        return
    for row in build_rows():
        print(f"{row['label']}: {row['math']} <- {row['concrete_syntax']!r}")
        print(f"  OWL: {row['owl_rendering']}")
        print(f"  Datalog: {row['datalog_rendering']}")


if __name__ == "__main__":
    main()
