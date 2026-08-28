"""
Assemble the full translation-table intermediate representation (IR):
primitive-formula rows (extract_primitives.py + renderings.py) and
structural rows (extract_structural.py), as one JSON document that every
renderer (LaTeX/Markdown/etc.) reads from -- no renderer talks to the
extraction modules directly.

Usage:
  python -m tools.translation_table.build_ir [--check] [-o OUTPUT.json]

  --check: verify every extracted primitive row has a renderings.py entry
  (fails loudly on drift -- a new/renamed primitive method with no
  hand-written rendering yet). Also runs extract_primitives.py's own
  --check (method-set divergence between the two transformers).
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools.translation_table.extract_primitives import build_rows as build_primitive_rows
from tools.translation_table.renderings import PRIMITIVE_RENDERINGS
from tools.translation_table.extract_structural import build_examples as build_structural_examples

# Hand-written descriptions for structural categories -- same spirit as
# renderings.py: extraction supplies real code output, a human supplies
# the framing prose. Kept here (not in extract_structural.py) so the
# extraction module stays pure "run the code, capture output."
STRUCTURAL_NOTES = {
    "indices": "One NamedIndividual per (moment, history) pair reached / one succ(...) fact per history-adjacent pair -- Datalog's fragment shown here covers both indices and succ facts together, since _generate_structural_facts emits them in one pass.",
    "succ": "succ declared FunctionalObjectProperty + a totality axiom (every individual has some succ-successor). Datalog has no equivalent explicit schema axiom -- totality is implicit in which succ(...) facts are asserted, not a separate declared constraint.",
    "succ_assertions": "Ground succ(from, to) facts, one per history-adjacent moment pair. On the Datalog side these are the same facts already shown under 'indices' (_generate_structural_facts emits both together) -- listed separately here only because OWL's succ-assertion code path is its own method.",
    "same_moment": "OWL's same_moment structure is STRATEGY-DEPENDENT (self.strategy.add_same_moment_structure, not a plain _add_* method) -- see EquivChainedNominalStrategy vs EquivFullCardinalityStrategy in index_strategies.py; not captured by this extractor, needs its own pass if wanted in the table. Datalog side: same_moment_base ground facts (not shown here, see 'indices') plus reflexive/transitive closure rules and top(I) defined as same_moment(I,I).",
    "action_disjointness": "OWL: DisjointClasses per agent-moment where >1 action type is available. Datalog: no explicit disjointness declaration found in the structural-facts/rules output inspected here -- action exclusivity isn't separately axiomed the way OWL declares it (worth double-checking this isn't a gap, not just an intentional omission, before publishing).",
    "action_assertions": "OWL: ClassAssertion per actual action taken, PLUS closed-world-assumption ObjectComplementOf assertions for every action NOT taken at that index (explicit negation). Datalog: plain action(I, 'name') facts only for actions taken -- negation is handled by Datalog's native closed-world assumption at query time, not asserted as explicit facts the way OWL needs to.",
    "opposing": "OWL: SubClassOf(opposed_action, Opp2<opposing_action>) directly. Datalog: a default '__never__' fact for every opposing_X predicate (closed-world default: nothing is opposed unless proven) plus a conditional rule opposing_sd1(I) <= action(I, 'ha2') deriving it when the opposing action is actually taken.",
    "propositions": "OWL: ClassAssertion(q) or ClassAssertion(ObjectComplementOf(q)) per index, matching the model's stated proposition/negation. Datalog: prop(I, 'q') or prop(I, '~q') facts, same information, string-based rather than class-based.",
}


def build_ir() -> dict:
    primitive_rows = build_primitive_rows()
    missing_renderings = {r.method_name for r in primitive_rows} - set(PRIMITIVE_RENDERINGS)
    if missing_renderings:
        raise RuntimeError(
            f"Primitive row(s) {missing_renderings} extracted from code have "
            f"no entry in renderings.py -- add one before building the IR."
        )

    primitives_ir = []
    for row in primitive_rows:
        rendering = PRIMITIVE_RENDERINGS[row.method_name]
        primitives_ir.append({
            "method_name": row.method_name,
            "alon_syntax": row.alon_syntax,
            "owl": {
                "shape": row.owl_shape,
                "rendering": rendering["owl"],
                "source": row.owl_source,
                "source_file": row.owl_file,
                "source_line": row.owl_line,
            },
            "datalog": {
                "shape": row.datalog_shape,
                "rendering": rendering["datalog"],
                "source": row.datalog_source,
                "source_file": row.datalog_file,
                "source_line": row.datalog_line,
            },
        })

    structural_examples = build_structural_examples()
    structural_ir = []
    for category, content in structural_examples.items():
        structural_ir.append({
            "category": category,
            "notes": STRUCTURAL_NOTES.get(category, "(no notes written yet)"),
            "owl_example": content["owl"],
            "datalog_example": content["datalog"],
        })

    return {
        "canonical_model": "streamlit_app/models/3.1.mmd",
        "primitives": primitives_ir,
        "structural": structural_ir,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args()

    ir = build_ir()

    if args.check:
        print(f"OK: {len(ir['primitives'])} primitive rows, {len(ir['structural'])} structural rows, no drift.")
        return

    output_path = args.output or (Path(__file__).parent / "translation_table.json")
    output_path.write_text(json.dumps(ir, indent=2))
    print(f"Wrote {output_path} ({len(ir['primitives'])} primitive rows, {len(ir['structural'])} structural rows)")


if __name__ == "__main__":
    main()
