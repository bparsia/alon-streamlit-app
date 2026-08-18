"""
Result registry for ALOn toolkit.

Maintains a versioned record of reasoning results across models, pipeline
versions, and serialiser variants. Each entry records:

  - which code commit produced the results
  - a content hash of the model input (so model changes are detectable)
  - per-formula results for each variant (datalog, owl_full_cardinality, ...)
  - cross-variant agreement
  - verification status and source

Entries are append-only. New runs add new entries; old ones are never
overwritten. Regressions are detected by comparing the current run against
the most recent verified entry for the same (model, variant).

Usage:
  # Capture current results and append to registry:
  python -m tests.registry capture --models 3.1 3.5 3.6 3.7

  # Verify (mark an entry as verified):
  python -m tests.registry verify --model 3.1 --commit f5b458c --source "book example"

  # Show summary table:
  python -m tests.registry show
"""

import hashlib
import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

REGISTRY_PATH = Path(__file__).parent / "fixtures" / "result_registry.json"
MODELS_DIR = Path(__file__).parent.parent / "streamlit_app" / "models"


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git_commit_hash() -> str:
    """Return the current HEAD commit hash (short)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
            cwd=Path(__file__).parent.parent,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _git_tag() -> Optional[str]:
    """Return the current git tag if HEAD is tagged, else None."""
    try:
        result = subprocess.run(
            ["git", "describe", "--exact-match", "--tags", "HEAD"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _model_hash(model_text: str) -> str:
    """SHA-256 (first 12 hex chars) of model text."""
    return hashlib.sha256(model_text.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Pipeline runners
# ---------------------------------------------------------------------------

def _setup_model(model_text: str):
    """Parse model and attach standard responsibility config. Returns model."""
    from alo_translator.parsers.dbt_parser import parse_dbt_diagram
    from alo_translator.parsers.builder import parse_formula
    from alo_translator.query_generation import ResponsibilityConfig, generate_queries

    model = parse_dbt_diagram(model_text)
    model.responsibility_config = ResponsibilityConfig(
        target_proposition="q", agents="all", groups="all",
        responsibility_types=["pres", "sres", "res", "dxstit", "but", "ness"],
        history="h1",
    )
    model.queries = generate_queries(model)
    for q in model.queries:
        if q.formula_ast is None:
            q.formula_ast = parse_formula(q.formula_string)
    return model


def _eval_metadata(model) -> Dict:
    """Extract eval index, outcome, and agent→action mapping from a parsed model."""
    eh = model.evaluation_history or "h1"
    em = model.evaluation_moment or ""
    outcome = (model.responsibility_config.target_proposition
               if model.responsibility_config else "")
    cga = {}
    if eh in model.histories and em:
        cga = model.histories[eh].actions_at.get(em, {})
    return {
        "eval_history": eh,
        "eval_moment": em,
        "outcome": outcome,
        "agent_actions": {agent: action for agent, action in cga.items()},
    }


def _run_datalog(model_text: str) -> Dict[str, bool]:
    """Run Datalog pipeline. Returns {formula: satisfied}."""
    from alo_translator.serializers.datalog import DatalogIndexSerializer

    model = _setup_model(model_text)
    serializer = DatalogIndexSerializer(model, evaluation_history="h1")
    results = serializer.evaluate()
    id_to_formula = {q.query_id: q.formula_string for q in model.queries}
    return {
        id_to_formula[qid]: r.get("result", False)
        for qid, r in results.items()
        if qid in id_to_formula
    }


def _run_owl(model_text: str, strategy_name: str) -> Optional[Dict[str, bool]]:
    """Run OWL+Konclude pipeline. Returns {formula: satisfied} or None if unavailable."""
    try:
        import tempfile
        from alo_translator.serializers.owl import OWLSerializer
        from alo_translator.serializers.index_strategies import EquivFullCardinalityStrategy
        from alo_translator.reasoners.konclude import KoncludeAdapter
        from alo_translator.reasoners.base import ReasoningMode
        from alo_translator.reasoners.config import load_config

        root = Path(__file__).parent.parent
        konclude_path = None
        for config_path in [root / "reasoner_config.toml"]:
            if config_path.exists():
                try:
                    config = load_config(config_path)
                    p = Path(config.reasoners["konclude"].path)
                    if not p.is_absolute():
                        p = config_path.parent / p
                    if p.exists():
                        konclude_path = p
                        break
                except Exception:
                    pass
        if konclude_path is None:
            return None

        strategy_map = {"owl_full_cardinality": EquivFullCardinalityStrategy()}
        strategy = strategy_map.get(strategy_name)
        if strategy is None:
            return None

        model = _setup_model(model_text)

        serializer = OWLSerializer(model,
                                   evaluation_history=model.evaluation_history,
                                   evaluation_moment=model.evaluation_moment,
                                   strategy=strategy)
        owl_str = serializer.serialize()

        with tempfile.NamedTemporaryFile(suffix=".owl", mode="w", delete=False) as f:
            f.write(owl_str)
            owl_path = Path(f.name)

        try:
            adapter = KoncludeAdapter(str(konclude_path))
            result = adapter.run(owl_path, mode=ReasoningMode.REALISATION, timeout=600)
        finally:
            owl_path.unlink(missing_ok=True)

        if not result.success:
            return None

        m_types = result.individual_types.get("m_h1", set())
        id_to_formula = {q.query_id: q.formula_string for q in model.queries}
        formula_set = {id_to_formula[q.query_id] for q in model.queries
                       if q.query_id in m_types and q.query_id in id_to_formula}
        return {
            id_to_formula[q.query_id]: (id_to_formula[q.query_id] in formula_set)
            for q in model.queries
            if q.query_id in id_to_formula
        }
    except Exception as e:
        print(f"  OWL/{strategy_name} failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------

def load_registry() -> List[dict]:
    if not REGISTRY_PATH.exists():
        return []
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def save_registry(entries: List[dict]):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w") as f:
        json.dump(entries, f, indent=2)


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

def capture(model_ids: List[str], variants: List[str] = None):
    """Run specified models through all available variants and append to registry."""
    if variants is None:
        variants = ["datalog", "owl_full_cardinality"]

    commit = _git_commit_hash()
    tag = _git_tag()
    today = date.today().isoformat()

    entries = load_registry()

    for model_id in model_ids:
        mmd_path = MODELS_DIR / f"{model_id}.mmd"
        if not mmd_path.exists():
            print(f"Model {model_id}: file not found, skipping")
            continue

        model_text = mmd_path.read_text()
        model_hash = _model_hash(model_text)
        print(f"\nModel {model_id} (hash={model_hash}, commit={commit}):")

        # Parse model once to get eval metadata
        meta = _eval_metadata(_setup_model(model_text))

        variant_results: Dict[str, Dict[str, bool]] = {}

        for variant in variants:
            print(f"  Running {variant}...", end=" ", flush=True)
            if variant == "datalog":
                results = _run_datalog(model_text)
            elif variant.startswith("owl_"):
                results = _run_owl(model_text, variant)
            else:
                print("unknown variant, skipping")
                continue

            if results is None:
                print("unavailable")
                continue

            satisfied_count = sum(1 for v in results.values() if v)
            print(f"{satisfied_count}/{len(results)} satisfied")
            variant_results[variant] = results

        if not variant_results:
            print(f"  No results — skipping entry")
            continue

        # Cross-check: compare all pairs
        cross_check = {}
        variant_names = list(variant_results.keys())
        for i in range(len(variant_names)):
            for j in range(i + 1, len(variant_names)):
                a, b = variant_names[i], variant_names[j]
                ra, rb = variant_results[a], variant_results[b]
                common = set(ra) & set(rb)
                disagree = [f for f in common if ra[f] != rb[f]]
                key = f"{a}_vs_{b}"
                cross_check[key] = "agree" if not disagree else f"disagree on: {sorted(disagree)}"

        # Build per-formula result matrix
        all_formulas = sorted(set(f for r in variant_results.values() for f in r))
        formula_results = []
        for formula in all_formulas:
            row: Dict = {"formula": formula}
            for variant, results in variant_results.items():
                if formula in results:
                    row[variant] = results[formula]
            formula_results.append(row)

        entry = {
            "model": model_id,
            "model_hash": model_hash,
            "commit": commit,
            "tag": tag,
            "date": today,
            "eval_moment": meta["eval_moment"],
            "eval_history": meta["eval_history"],
            "outcome": meta["outcome"],
            "agent_actions": meta["agent_actions"],
            "variants_run": variant_names,
            "cross_check": cross_check,
            "verified": False,
            "source": None,
            "results": formula_results,
        }
        entries.append(entry)
        print(f"  Entry appended (cross_check: {cross_check})")

    save_registry(entries)
    print(f"\nRegistry saved to {REGISTRY_PATH} ({len(entries)} total entries)")
    return entries


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def verify(model_id: str, commit: str, source: str = None):
    """Mark the most recent entry for (model, commit) as verified."""
    entries = load_registry()
    matched = [e for e in entries if e["model"] == model_id and e["commit"] == commit]
    if not matched:
        print(f"No entry found for model={model_id} commit={commit}")
        return
    entry = matched[-1]
    entry["verified"] = True
    if source:
        entry["source"] = source
    save_registry(entries)
    print(f"Marked verified: {model_id} @ {commit}" + (f" ({source})" if source else ""))


# ---------------------------------------------------------------------------
# Show
# ---------------------------------------------------------------------------

def show(model_id: str = None, verified_only: bool = False):
    """Print a summary table of registry entries."""
    entries = load_registry()
    if model_id:
        entries = [e for e in entries if e["model"] == model_id]
    if verified_only:
        entries = [e for e in entries if e["verified"]]

    if not entries:
        print("No entries.")
        return

    for entry in entries:
        verified_str = "✓ verified" if entry["verified"] else "  unverified"
        source_str = f" [{entry['source']}]" if entry.get("source") else ""
        print(f"\n{entry['model']} | {entry['commit']}"
              + (f" ({entry['tag']})" if entry.get("tag") else "")
              + f" | {entry['date']} | {verified_str}{source_str}")
        print(f"  model_hash: {entry['model_hash']}")
        print(f"  variants: {', '.join(entry['variants_run'])}")
        for k, v in entry.get("cross_check", {}).items():
            print(f"  {k}: {v}")

        # Summary: count satisfied per variant
        for variant in entry["variants_run"]:
            sat = [r for r in entry["results"] if r.get(variant) is True]
            total = [r for r in entry["results"] if variant in r]
            print(f"  {variant}: {len(sat)}/{len(total)} satisfied")


# ---------------------------------------------------------------------------
# Regression check (used by tests)
# ---------------------------------------------------------------------------

def get_verified_entries(model_id: str) -> List[dict]:
    """Return all verified registry entries for a given model."""
    return [e for e in load_registry() if e["model"] == model_id and e["verified"]]


def check_regression(model_id: str, variant: str, current: Dict[str, bool]) -> List[str]:
    """
    Compare current results against the most recent verified entry.

    Returns list of disagreement strings (empty = no regression).
    """
    verified = get_verified_entries(model_id)
    if not verified:
        return []  # No baseline to compare against

    # Most recent verified entry that includes this variant
    baseline = None
    for entry in reversed(verified):
        if variant in entry.get("variants_run", []):
            baseline = entry
            break
    if baseline is None:
        return []

    disagreements = []
    for row in baseline["results"]:
        formula = row["formula"]
        if variant not in row:
            continue
        expected = row[variant]
        actual = current.get(formula)
        if actual is None:
            disagreements.append(f"{formula}: missing from current run")
        elif actual != expected:
            disagreements.append(
                f"{formula}: was {expected}, now {actual} "
                f"(baseline: {baseline['commit']} {baseline['date']})"
            )
    return disagreements


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ALOn result registry")
    sub = parser.add_subparsers(dest="cmd")

    p_capture = sub.add_parser("capture", help="Run models and append to registry")
    p_capture.add_argument("--models", nargs="+", default=["3.1", "3.5", "3.6", "3.7"])
    p_capture.add_argument("--variants", nargs="+", default=["datalog", "owl_full_cardinality"])

    p_verify = sub.add_parser("verify", help="Mark an entry as verified")
    p_verify.add_argument("--model", required=True)
    p_verify.add_argument("--commit", required=True)
    p_verify.add_argument("--source", default=None)

    p_show = sub.add_parser("show", help="Show registry summary")
    p_show.add_argument("--model", default=None)
    p_show.add_argument("--verified-only", action="store_true")

    args = parser.parse_args()

    if args.cmd == "capture":
        capture(args.models, args.variants)
    elif args.cmd == "verify":
        verify(args.model, args.commit, args.source)
    elif args.cmd == "show":
        show(args.model, getattr(args, "verified_only", False))
    else:
        parser.print_help()
