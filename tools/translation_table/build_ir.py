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
from tools.translation_table.extract_structural import build_rows as build_structural_rows


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
            "ascii_syntax": row.ascii_syntax,
            "owl": {
                "shape": row.owl_shape,
                "rendering": rendering["owl"],
                "source": row.owl_source,
                "source_file": row.owl_file,
                "source_line": row.owl_line,
            },
            "sparql": {
                "shape": row.sparql_shape,
                "rendering": rendering["sparql"],
                "source": row.sparql_source,
                "source_file": row.sparql_file,
                "source_line": row.sparql_line,
            },
            "datalog": {
                "shape": row.datalog_shape,
                "rendering": rendering["datalog"],
                "source": row.datalog_source,
                "source_file": row.datalog_file,
                "source_line": row.datalog_line,
            },
        })

    structural_ir = build_structural_rows()

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
