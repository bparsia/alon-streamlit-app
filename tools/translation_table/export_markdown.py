"""
Export the translation-table IR (build_ir.py's output) to a Markdown
table -- meant as an editable surface (pastable into a text editor,
Google Sheets, or any online Markdown/CSV table editor), NOT as a
publication target. render_latex.py remains the publication path.

LaTeX cell content (math notation, \\texttt{} identifiers) is passed
through as-is rather than converted to plain text -- GitHub/most
Markdown viewers with KaTeX support render inline $...$ fine, and
round-tripping exact LaTeX back into render_latex.py later is simpler
if this export doesn't lossily rewrite it.

One-way export only (JSON IR -> Markdown). No import path back into the
JSON IR yet -- editing the Markdown does not currently feed back into
build_ir.py/render_latex.py. If/when that's wanted, this is the file to
extend.

Usage:
  python -m tools.translation_table.export_markdown [-o OUTPUT.md]
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

IR_PATH = Path(__file__).parent / "translation_table.json"


def _md_cell(text: str) -> str:
    """Collapse newlines for a Markdown table cell (cells can't contain
    literal line breaks). Does NOT escape `|` -- the only `|` in the
    current IR is a math-mode absolute-value bar (e.g. $|\\mathcal{H}_m|$),
    not a literal table delimiter, and escaping it would corrupt the
    LaTeX. If a genuine unescaped delimiter-breaking `|` shows up later,
    fix it at the source (IR) rather than blind-escaping here."""
    return " ".join(text.split())


def render_structural_syntax_table(ir: dict) -> str:
    lines = [
        "## Model structure: syntax reference",
        "",
        "| Denotes | .mmd syntax |",
        "|---|---|",
    ]
    for row in ir["structural"]:
        lines.append(f"| {_md_cell(row['math'])} | {_md_cell(row['concrete_syntax'])} |")
    return "\n".join(lines) + "\n"


def render_primitives_syntax_table(ir: dict) -> str:
    lines = [
        "## Formula grammar: syntax reference",
        "",
        "| ALOn | ASCII syntax |",
        "|---|---|",
    ]
    for row in ir["primitives"]:
        lines.append(f"| {_md_cell(row['alon_syntax'])} | {_md_cell(row['ascii_syntax'])} |")
    return "\n".join(lines) + "\n"


def render_structural_dl_table(ir: dict) -> str:
    """OWL and SPARQL paired -- see render_latex.render_structural_dl_table's
    docstring for why (SPARQL queries the same OWL ontology's ABox/
    structural-TBox rather than deriving a separate translation)."""
    lines = [
        "## Model structure: translation (OWL / SPARQL)",
        "",
        "| .mmd syntax | OWL | SPARQL |",
        "|---|---|---|",
    ]
    for row in ir["structural"]:
        lines.append(
            f"| {_md_cell(row['concrete_syntax'])} "
            f"| {_md_cell(row['owl_rendering'])} | {_md_cell(row['sparql_rendering'])} |"
        )
    return "\n".join(lines) + "\n"


def render_primitives_dl_table(ir: dict) -> str:
    lines = [
        "## Formula grammar: translation (OWL / SPARQL)",
        "",
        "| ASCII syntax | OWL | SPARQL |",
        "|---|---|---|",
    ]
    for row in ir["primitives"]:
        owl = row["owl"]["rendering"]
        sparql = row["sparql"]["rendering"]
        lines.append(f"| {_md_cell(row['ascii_syntax'])} | {_md_cell(owl)} | {_md_cell(sparql)} |")
    return "\n".join(lines) + "\n"


def render_structural_datalog_table(ir: dict) -> str:
    """pyDatalog kept separate -- a genuinely different reasoning
    paradigm, not a third column alongside OWL/SPARQL."""
    lines = [
        "## Model structure: translation (pyDatalog)",
        "",
        "| .mmd syntax | pyDatalog |",
        "|---|---|",
    ]
    for row in ir["structural"]:
        lines.append(f"| {_md_cell(row['concrete_syntax'])} | {_md_cell(row['datalog_rendering'])} |")
    return "\n".join(lines) + "\n"


def render_primitives_datalog_table(ir: dict) -> str:
    lines = [
        "## Formula grammar: translation (pyDatalog)",
        "",
        "| ASCII syntax | pyDatalog |",
        "|---|---|",
    ]
    for row in ir["primitives"]:
        datalog = row["datalog"]["rendering"]
        lines.append(f"| {_md_cell(row['ascii_syntax'])} | {_md_cell(datalog)} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args()

    if not IR_PATH.exists():
        print(f"No IR found at {IR_PATH} -- run: python -m tools.translation_table.build_ir", file=sys.stderr)
        sys.exit(1)
    ir = json.loads(IR_PATH.read_text())

    header = "<!-- Exported by tools/translation_table/export_markdown.py -- editable, one-way export from translation_table.json. -->\n"
    tables = [
        render_structural_syntax_table(ir),
        render_primitives_syntax_table(ir),
        render_structural_dl_table(ir),
        render_primitives_dl_table(ir),
        render_structural_datalog_table(ir),
        render_primitives_datalog_table(ir),
    ]
    output = header + "\n" + "\n".join(tables)

    output_path = args.output or (Path(__file__).parent / "translation_table.md")
    output_path.write_text(output)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
