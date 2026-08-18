"""
Registry review TUI for ALOn toolkit.

Interactive review of reasoning results in the result registry.
Supports verifying/rejecting entries and exporting to CSV.

Usage:
  python -m tests.review                    # review all unverified entries
  python -m tests.review --all              # include already-verified entries
  python -m tests.review --model 3.1        # filter by model
  python -m tests.review --export out.csv   # export registry to CSV and exit
"""

import csv
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Label, Static

try:
    from tests.registry import load_registry, save_registry, REGISTRY_PATH
except ModuleNotFoundError:
    from registry import load_registry, save_registry, REGISTRY_PATH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _disagree_summary(entry: dict) -> str:
    cc = entry.get("cross_check", {})
    if not cc:
        return "—"
    issues = [v for v in cc.values() if v != "agree"]
    return f"{len(issues)} disagree" if issues else "agree"


def _verified_str(entry: dict) -> str:
    if entry.get("verified"):
        return "✓"
    return ""


def _variants_str(entry: dict) -> str:
    return ", ".join(entry.get("variants_run", []))


OPERATORS = ["pres", "sres", "res", "dxstit", "but", "ness"]
_OP_NORM = {op.lower(): op for op in OPERATORS}  # case-insensitive lookup


def _parse_formula(formula: str):
    """Parse a formula string into (agent_key, operator).

    Returns (agent_key, op) or None if unrecognised.
    agent_key is a canonical sortable string.
    """
    import re
    # [agent op]prop  e.g. "[1 pres]q", "[{1, 2} DXSTIT]q"
    m = re.match(r'^\[(.+?) (\w+)\]\w+$', formula)
    if m:
        agent, op = m.group(1).strip(), _OP_NORM.get(m.group(2).lower())
        if op:
            return agent, op

    # op(action, prop)  e.g. "but(sd1, q)", "ness({1:sd, 2:ss}, q)"
    m = re.match(r'^(\w+)\((.+?),\s*\w+\)$', formula)
    if m:
        op, agent = _OP_NORM.get(m.group(1).lower()), m.group(2).strip()
        if op:
            return agent, op

    return None


def _pivot_results(entry: dict) -> tuple[list[str], list[dict]]:
    """Pivot registry results into agent×operator grid.

    Uses agent_actions mapping (if present) to fold but/ness action-keyed
    formulas back onto their agent rows.

    Returns (variants, rows) where each row is:
      {"agent": str, op: {variant: "T"/"F"/"—"}, ..., "disagree": bool}
    """
    import re
    variants = entry.get("variants_run", [])
    # action_str -> agent (e.g. "sd1" -> "1", "ss2" -> "2")
    agent_actions = entry.get("agent_actions", {})  # {agent: action_type}
    # Map action strings used in formulas (e.g. "sd1" = action_type+agent) back to agent
    action_to_agent = {f"{act}{agent}": agent
                       for agent, act in agent_actions.items()}
    # Also handle group actions: "{1:sd, 2:ss}" -> agent key doesn't apply directly,
    # leave those as-is (they'll form their own row)

    # grid[agent][op][variant] = bool
    grid: dict[str, dict[str, dict[str, bool]]] = {}

    def _get_or_create(agent):
        if agent not in grid:
            grid[agent] = {o: {} for o in OPERATORS}
        return grid[agent]

    def _canonical_agent(raw_agent: str, op: str) -> str:
        """Normalise agent key to agent-set form.

        Individual but/ness: "sd1" -> "1" via action_to_agent.
        Group but/ness: "{1:sd, 2:ss}" -> "{1, 2}" to merge with resp rows.
        """
        import re
        if op in ("but", "ness"):
            # Individual action string e.g. "sd1"
            if raw_agent in action_to_agent:
                return action_to_agent[raw_agent]
            # Group action string e.g. "{1:sd, 2:ss}"
            m = re.match(r'^\{(.+)\}$', raw_agent)
            if m:
                agents = sorted(p.split(':')[0].strip() for p in m.group(1).split(','))
                return '{' + ', '.join(agents) + '}'
        return raw_agent

    for r in entry.get("results", []):
        parsed = _parse_formula(r["formula"])
        if parsed is None:
            continue
        raw_agent, op = parsed
        agent = _canonical_agent(raw_agent, op)
        _get_or_create(agent)
        for v in variants:
            if v in r:
                grid[agent][op][v] = r[v]

    # Sort: individuals (no braces) first, then groups by size
    def _agent_sort_key(a):
        return (0 if re.match(r'^\w+$', a) else 1, len(a), a)

    rows = []
    for agent in sorted(grid.keys(), key=_agent_sort_key):
        row = {"agent": agent}
        disagree = False
        for op in OPERATORS:
            cell = {}
            for v in variants:
                val = grid[agent][op].get(v)
                cell[v] = ("T" if val else "F") if val is not None else "—"
            actual_vals = [grid[agent][op][v] for v in variants if v in grid[agent][op]]
            if len(set(actual_vals)) > 1:
                disagree = True
            row[op] = cell
        row["disagree"] = disagree
        rows.append(row)
    return variants, rows


def export_csv(entries: list[dict], path: Path):
    """Export registry entries to CSV (one row per formula per entry)."""
    rows = []
    for e in entries:
        base = {
            "model": e["model"],
            "commit": e["commit"],
            "date": e["date"],
            "verified": e.get("verified", False),
            "source": e.get("source", ""),
        }
        for r in e.get("results", []):
            row = dict(base)
            row["formula"] = r["formula"]
            for variant in e.get("variants_run", []):
                row[variant] = r.get(variant, "")
            rows.append(row)

    if not rows:
        print("No data to export.")
        return

    fieldnames = ["model", "commit", "date", "verified", "source", "formula"]
    all_variants = sorted({k for r in rows for k in r if k not in fieldnames})
    fieldnames += all_variants

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Exported {len(rows)} rows to {path}")


# ---------------------------------------------------------------------------
# Source note input screen
# ---------------------------------------------------------------------------

class ConfirmScreen(Screen):
    """Modal yes/no confirmation."""

    BINDINGS = [
        Binding("escape", "dismiss(False)", "Cancel"),
    ]

    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)
        self.message = message

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(self.message),
            Button("Verify", id="btn_yes", variant="success"),
            Button("Cancel", id="btn_no", variant="default"),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn_yes")


# ---------------------------------------------------------------------------
# Formula detail screen
# ---------------------------------------------------------------------------

class FormulaScreen(Screen):
    """Per-formula result table for a single registry entry.

    Cells show T/F per variant. Click or press Enter/Space to toggle a cell.
    Press v to verify (saves any edits + marks verified).
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen()", "Back"),
        Binding("v", "verify", "Verify"),
        Binding("space", "toggle_cell", "Toggle cell"),
        Binding("e", "export_csv", "Export CSV"),
        Binding("q", "app.quit()", "Quit"),
    ]

    def __init__(self, entry: dict, entry_index: int, entry_list=None, list_idx: int = 0, **kwargs):
        super().__init__(**kwargs)
        self.entry = entry
        self.entry_index = entry_index
        self.entry_list = entry_list
        self.list_idx = list_idx
        # _grid[row_idx][col_idx] = current display value ("T", "F", or "—")
        self._grid: list[list[str]] = []
        self._variants: list[str] = []
        self._col_is_data: list[bool] = []  # True if column holds a T/F value
        # _cell_key[row][col] = (agent, op, variant) or None
        self._cell_key: list[list[Optional[tuple]]] = []
        self._pivot_rows: list[dict] = []

    def _header_str(self) -> str:
        e = self.entry
        status = "✓ verified" if e.get("verified") else "unverified"
        source = f" [{e['source']}]" if e.get("source") else ""
        em = e.get("eval_moment", "")
        eh = e.get("eval_history", "")
        outcome = e.get("outcome", "")
        index_str = f"  |  Index: {em}/{eh}" if em and eh else ""
        outcome_str = f"  |  Outcome: {outcome}" if outcome else ""
        return (f"Model: {e['model']}  |  Commit: {e['commit']}  |  "
                f"Date: {e['date']}{index_str}{outcome_str}  |  {status}{source}")

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._header_str(), id="entry_header")
        yield DataTable(id="formula_table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#formula_table", DataTable)
        table.cursor_type = "cell"

        variants, rows = _pivot_results(self.entry)
        self._variants = variants
        self._pivot_rows = rows
        multi = len(variants) > 1

        # Build column metadata
        col_is_data = [False]  # agent column is not a data cell
        col_keys: list[Optional[tuple]] = [None]  # (op, variant) per column, None for non-data
        table.add_column("agent/coalition", width=24)
        for op in OPERATORS:
            if multi:
                for v in variants:
                    table.add_column(f"{op}/{v[:3]}", width=10)
                    col_is_data.append(True)
                    col_keys.append((op, v))
            else:
                table.add_column(op, width=8)
                col_is_data.append(True)
                col_keys.append((op, variants[0] if variants else None))
        if multi:
            table.add_column("!", width=3)
            col_is_data.append(False)
            col_keys.append(None)
        self._col_is_data = col_is_data
        self._col_keys = col_keys

        for row_idx, row in enumerate(rows):
            cells = [row["agent"]]
            cell_keys_row = [None]
            for op in OPERATORS:
                if multi:
                    for v in variants:
                        cells.append(row[op].get(v, "—"))
                        cell_keys_row.append((op, v))
                else:
                    cells.append(row[op].get(variants[0], "—") if variants else "—")
                    cell_keys_row.append((op, variants[0] if variants else None))
            if multi:
                cells.append("✗" if row["disagree"] else "")
                cell_keys_row.append(None)
            table.add_row(*cells)
            self._grid.append(list(cells))
            self._cell_key.append(cell_keys_row)

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        self._toggle(event.coordinate.row, event.coordinate.column)

    def action_toggle_cell(self) -> None:
        table = self.query_one("#formula_table", DataTable)
        self._toggle(table.cursor_row, table.cursor_column)

    def _toggle(self, row: int, col: int) -> None:
        if col >= len(self._col_is_data) or not self._col_is_data[col]:
            return
        current = self._grid[row][col]
        if current == "—":
            return  # no query for this cell — can't toggle
        new_val = "F" if current == "T" else "T"
        self._grid[row][col] = new_val
        table = self.query_one("#formula_table", DataTable)
        table.update_cell_at((row, col), new_val)

    def _save_edits(self) -> None:
        """Write any toggled cells back into the registry entry's results."""
        # Build edit map: {(agent, op, variant): bool}
        edits: dict[tuple, bool] = {}
        for row_idx, row_keys in enumerate(self._cell_key):
            agent = self._grid[row_idx][0]
            for col_idx, key in enumerate(row_keys):
                if key is None:
                    continue
                op, variant = key
                val = self._grid[row_idx][col_idx]
                if val != "—":
                    edits[(agent, op, variant)] = (val == "T")

        # Apply back to entry results
        agent_actions = self.entry.get("agent_actions", {})
        action_to_agent = {f"{act}{ag}": ag for ag, act in agent_actions.items()}

        import re
        def _canonical(ra, op):
            if op in ("but", "ness"):
                if ra in action_to_agent:
                    return action_to_agent[ra]
                m = re.match(r'^\{(.+)\}$', ra)
                if m:
                    agents = sorted(p.split(':')[0].strip() for p in m.group(1).split(','))
                    return '{' + ', '.join(agents) + '}'
            return ra

        for r in self.entry.get("results", []):
            parsed = _parse_formula(r["formula"])
            if parsed is None:
                continue
            raw_agent, op = parsed
            agent = _canonical(raw_agent, op)
            for v in self._variants:
                if (agent, op, v) in edits and v in r:
                    r[v] = edits[(agent, op, v)]

    def action_verify(self) -> None:
        def _on_confirm(confirmed: bool) -> None:
            if not confirmed:
                return
            self._save_edits()
            entries = load_registry()
            entries[self.entry_index] = self.entry
            entries[self.entry_index]["verified"] = True
            entries[self.entry_index]["source"] = f"reviewed {date.today().isoformat()}"
            save_registry(entries)
            self.entry = entries[self.entry_index]
            self.query_one("#entry_header", Static).update(self._header_str())
            if self.entry_list is not None:
                self.entry_list.entries[self.list_idx] = self.entry
                t = self.entry_list.query_one("#entry_table", DataTable)
                t.update_cell_at((self.list_idx, 4), _verified_str(self.entry))
                t.update_cell_at((self.list_idx, 6), self.entry.get("source") or "")

        self.app.push_screen(
            ConfirmScreen("Do you believe all cells are (now) correct?"),
            _on_confirm,
        )

    def action_export_csv(self) -> None:
        path = Path(f"review_{self.entry['model']}_{self.entry['commit']}.csv")
        export_csv([self.entry], path)
        self.notify(f"Exported to {path}")


# ---------------------------------------------------------------------------
# Entry list screen
# ---------------------------------------------------------------------------

class EntryListScreen(Screen):
    """Top-level list of registry entries."""

    BINDINGS = [
        Binding("e", "export_all_csv", "Export all CSV"),
        Binding("q", "app.quit()", "Quit"),
    ]

    def __init__(self, entries: list[dict], **kwargs):
        super().__init__(**kwargs)
        self.entries = entries

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="entry_table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#entry_table", DataTable)
        table.cursor_type = "row"
        table.add_column("model", width=8)
        table.add_column("commit", width=10)
        table.add_column("date", width=12)
        table.add_column("variants", width=30)
        table.add_column("verified", width=10)
        table.add_column("cross-check", width=16)
        table.add_column("source", width=40)

        for e in self.entries:
            table.add_row(
                e["model"],
                e["commit"],
                e["date"],
                _variants_str(e),
                _verified_str(e),
                _disagree_summary(e),
                e.get("source") or "",
                key=str(id(e)),
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = event.cursor_row
        entry = self.entries[idx]
        all_entries = load_registry()
        full_idx = next(
            (i for i, e in enumerate(all_entries)
             if e["model"] == entry["model"] and e["commit"] == entry["commit"]
             and e["date"] == entry["date"]),
            idx,
        )
        self.app.push_screen(FormulaScreen(entry, full_idx, entry_list=self, list_idx=idx))

    def action_export_all_csv(self) -> None:
        path = Path("review_export.csv")
        export_csv(self.entries, path)
        self.notify(f"Exported {len(self.entries)} entries to {path}")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class ReviewApp(App):
    """ALOn registry review TUI."""

    TITLE = "ALOn Registry Review"
    CSS = """
    #entry_header {
        padding: 1;
        background: $surface;
        border: solid $primary;
        margin-bottom: 1;
    }
    DataTable {
        height: 1fr;
    }
    ConfirmScreen Vertical {
        align: center middle;
        width: 60;
        height: 10;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }
    ConfirmScreen Label {
        margin-bottom: 1;
    }
    ConfirmScreen Button {
        margin: 0 1;
    }
    """

    def __init__(self, entries: list[dict], **kwargs):
        super().__init__(**kwargs)
        self._entries = entries

    def on_mount(self) -> None:
        self.push_screen(EntryListScreen(self._entries))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="ALOn registry review TUI")
    parser.add_argument("--all", action="store_true", help="Include verified entries")
    parser.add_argument("--model", default=None, help="Filter by model ID")
    parser.add_argument("--export", default=None, metavar="PATH",
                        help="Export registry to CSV and exit (no TUI)")
    args = parser.parse_args()

    entries = load_registry()

    if args.model:
        entries = [e for e in entries if e["model"] == args.model]

    if not getattr(args, "all", False):
        entries = [e for e in entries if not e.get("verified")]

    if args.export:
        export_csv(entries if entries else load_registry(), Path(args.export))
        return

    if not entries:
        print("No entries to review. Use --all to include verified entries.")
        return

    app = ReviewApp(entries)
    app.run()


if __name__ == "__main__":
    main()
