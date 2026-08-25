"""
Sync a per-agent responsibility-results table (pres/sres/res/dxstit/but/
ness checkmarks, one row per agent) into a paper's .tex source, in place.

This is the per-agent counterpart to sync_paper_tables.py, which handles
per-*model* summary tables (table_models.tex/table_translations.tex).
This script handles the other table shape produced by this project:
format_layered_results_table() in streamlit_app/utils.py, which is one
row per agent for one (model, moment, history, target) eval point.

Unlike sync_paper_tables.py's row-matching (needed because paper authors
hand-edit per-model summary rows), this table's row set (the agent list
for one eval point) is small and derived entirely from the model, so
every run does a full regenerate of the block content -- no row-level
merge logic. Header/column-spec/caption/label OUTSIDE the marker block
are, as always, left untouched.

Marker format (paired, put directly in the paper .tex, body can start
empty or already contain a previous run's output -- always fully
replaced):

    % BEGIN RESULT TABLE: <model>.mmd @ <moment>/<history>/<target>

    % END RESULT TABLE: <model>.mmd @ <moment>/<history>/<target>

The <model>/<moment>/<history>/<target> in the marker is the source of
truth for what to (re)generate -- not a config file, not a CLI arg per
table. Add a new marker wherever a new per-agent table is needed; run
the script to fill/refresh every marker found in the target file(s).

Usage:
  cd papers/2026Fear && ../../.venv/bin/python3 sync_result_table.py <target.tex> [<target.tex> ...]
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from alo_translator.parsers.dbt_parser import parse_dbt_diagram
from streamlit_app.utils import run_analysis_datalog_layered, format_layered_results_table

MODELS_DIR = Path(__file__).parent / "models"

MARKER_RE = re.compile(
    r"% BEGIN RESULT TABLE: (?P<model>\S+) @ (?P<point>\S+)\n"
    r"(?P<body>.*?)"
    r"% END RESULT TABLE: (?P=model) @ (?P=point)\n",
    re.DOTALL,
)


def compute_table(model_file: str, moment: str, history: str, target: str) -> str:
    """Return just the \\begin{tabular}...\\end{tabular} block, without the
    "At m/h1, CGA:..." header line format_layered_results_table also
    produces. Every marker this script handles covers exactly one eval
    point, so that context belongs in the surrounding \\caption (paper
    prose) instead of being repeated in generated text. A block that
    shows MULTIPLE eval points together (like the isabella figure, which
    interleaves 4 point-labelled tables) genuinely needs the header line
    per block to disambiguate them -- that's a different marker type,
    not something this function should also try to serve.
    """
    mmd_path = MODELS_DIR / model_file
    if not mmd_path.exists():
        raise FileNotFoundError(f"No such model: {mmd_path}")
    model = parse_dbt_diagram(mmd_path.read_text())
    model.evaluation_moment = moment
    model.evaluation_history = history
    model.target_proposition = target
    model.evaluations = [(moment, history, target)]
    satisfied = run_analysis_datalog_layered(model)
    if satisfied is None:
        raise RuntimeError(f"Analysis failed for {model_file} @ {moment}/{history}/{target}")
    full = format_layered_results_table(model, satisfied, fmt="latex")
    tabular_start = full.index(r"\begin{tabular}")
    return full[tabular_start:]


def sync_file(path: Path) -> bool:
    text = path.read_text()

    def repl(m):
        model_file = m.group("model")
        point = m.group("point")
        moment, history, target = point.split("/", 2)
        table = compute_table(model_file, moment, history, target)
        return (
            f"% BEGIN RESULT TABLE: {model_file} @ {point}\n"
            f"{table}\n"
            f"% END RESULT TABLE: {model_file} @ {point}\n"
        )

    new_text, n = MARKER_RE.subn(repl, text)
    if n == 0:
        print(f"  (no result-table markers found in {path})", file=sys.stderr)
        return False
    if new_text != text:
        path.write_text(new_text)
        print(f"  updated {n} block(s) in {path}", file=sys.stderr)
        return True
    print(f"  {n} block(s) in {path}, no changes", file=sys.stderr)
    return False


def main():
    targets = [Path(p) for p in sys.argv[1:]]
    if not targets:
        print("Usage: sync_result_table.py <target.tex> [<target.tex> ...]", file=sys.stderr)
        sys.exit(1)

    for path in targets:
        print(f"Syncing {path}...", file=sys.stderr)
        sync_file(path)


if __name__ == "__main__":
    main()
