"""
Generate LaTeX tables (model shape, translation size + performance) for the
2026Fear paper, covering the models in papers/2026Fear/models/.

Each model is analyzed at every (moment, history, target) point in its
res_analyse list (or the single default evaluation point if res_analyse is
absent). Facts/rules/axioms are counted as the union of distinct
facts/rules/axioms across all eval points (not summed) -- each eval point's
serializer rebuilds the whole structural program/ontology from scratch, so
summing would count identical shared structure once per eval point. Wall-
clock time is the average per eval point (total time / number of eval
points) -- each eval point is a separate evaluate()/Konclude run, and since
models have different numbers of eval points, summing would conflate "cost
per query" with "how many queries this model happens to define," making a
model with more eval points look slower even if each individual run is
cheap.

Usage:
  cd papers/2026Fear && ../../.venv/bin/python3 generate_tables.py
Outputs:
  table_models.tex
  table_translations.tex
"""

import re
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from alo_translator.parsers.dbt_parser import parse_dbt_diagram
from alo_translator.serializers.datalog import DatalogIndexSerializer
from alo_translator.serializers.owl import OWLSerializer
from alo_translator.serializers.index_strategies import EquivFullCardinalityStrategy
from alo_translator.reasoners.konclude import KoncludeAdapter
from alo_translator.reasoners.base import ReasoningMode
from streamlit_app.utils import setup_layered_queries, konclude_path

MODELS_DIR = Path(__file__).parent / "models"
OUT_DIR = Path(__file__).parent
KONCLUDE_TIMEOUT = 1200  # 3.5's 16 histories can run well past 600s under load (Konclude runs under Rosetta on Apple Silicon)


def tex_escape(s: str) -> str:
    return s.replace("_", r"\_")


def eval_points_for(model):
    return model.require_evaluations()


def max_possible_eval_points(model) -> int:
    """Count non-leaf (moment, history) pairs -- the space res_analyse entries draw from."""
    total = 0
    for hp in model.histories.values():
        for moment_name in hp.path:
            node = model.moments.get(moment_name)
            if node is not None and not node.is_leaf:
                total += 1
    return total


def model_shape_stats(model) -> dict:
    agents_total = set()
    actions_total = set()  # (agent, action_type) pairs -- an agent's own action vocabulary
    agents_max_per_moment = 0
    actions_max_per_moment = 0
    for node in model.moments.values():
        agents_here = set(node.available_actions.keys())
        actions_here = {
            (agent, a) for agent, acts in node.available_actions.items() for a in acts
        }
        agents_total |= agents_here
        actions_total |= actions_here
        agents_max_per_moment = max(agents_max_per_moment, len(agents_here))
        actions_max_per_moment = max(actions_max_per_moment, len(actions_here))

    eps = eval_points_for(model)
    return {
        "moments": len(model.moments),
        "histories": len(model.histories),
        "depth": model.depth(),
        "agents_total": len(agents_total),
        "agents_max": agents_max_per_moment,
        "actions_total": len(actions_total),
        "actions_max": actions_max_per_moment,
        "eval_points_actual": len(eps),
        "eval_points_max": max_possible_eval_points(model),
    }


def datalog_line_sets(program: str) -> dict:
    """Return sets of distinct fact/rule lines, predicate names, and constants.

    Sets (not counts) so that callers can union across eval points and count
    distinct facts/rules/predicates/constants rather than summing duplicates
    -- the structural facts (moments, histories, actions, succ, same_moment)
    are identical across every eval point of the same model, since
    serialize() rebuilds the whole program from scratch each time.

    "predicates" is EDB (fact-defined: action, succ, prop, ...) + IDB
    (rule-defined: same_moment, top, bottom, derived query predicates)
    combined -- the Datalog analog of OWL's Classes+Properties vocabulary.
    "constants" is the distinct quoted string literals appearing in facts/
    rules (moment/history indices, action names, proposition symbols) --
    the Datalog analog of OWL's named individuals.
    """
    facts, rules, predicates, constants = set(), set(), set(), set()
    for l in program.splitlines():
        l = l.strip()
        if l.startswith("+"):
            facts.add(l)
            m = re.match(r"^\+\s*(\w+)\(", l)
            if m:
                predicates.add(m.group(1))
        elif "<=" in l:
            rules.add(l)
            m = re.match(r"^(\w+)\(", l)
            if m:
                predicates.add(m.group(1))
        else:
            continue
        constants.update(re.findall(r"'([^']*)'", l))
    return {
        "facts": facts,
        "rules": rules,
        "predicates": predicates,
        "constants": constants,
    }


TBOX_TAGS = {
    "SubClassOf", "DisjointClasses",
    "ReflexiveObjectProperty", "SymmetricObjectProperty", "FunctionalObjectProperty",
}
ABOX_TAGS = {"ClassAssertion", "ObjectPropertyAssertion", "DifferentIndividuals"}


def owl_axiom_sets(owl_xml: str) -> dict:
    """Return sets of distinct axiom strings per category, keyed by canonicalized XML.

    Sets (not counts) so that callers can union across eval points and count
    distinct axioms rather than summing duplicates -- the structural ABox/TBox
    (same_moment closure, action/succ assertions, etc.) is identical across
    every eval point of the same model, since serialize() rebuilds the whole
    ontology from scratch each time.

    "predicates" is Class + ObjectProperty declarations combined -- the OWL
    analog of Datalog's EDB+IDB predicate vocabulary. "individuals" is
    NamedIndividual declarations -- the OWL analog of Datalog's constants.
    """
    root = ET.fromstring(owl_xml)
    predicates, individuals, tbox, abox = set(), set(), set(), set()
    for child in root:
        tag = child.tag.split("}")[-1]
        key = ET.tostring(child, encoding="unicode")
        if tag == "Declaration":
            inner = child[0].tag.split("}")[-1]
            if inner in ("Class", "ObjectProperty"):
                predicates.add(key)
            elif inner == "NamedIndividual":
                individuals.add(key)
            else:
                raise ValueError(f"Unclassified OWL declaration kind: {inner!r}")
        elif tag in TBOX_TAGS:
            tbox.add(key)
        elif tag in ABOX_TAGS:
            abox.add(key)
        elif tag != "AnnotationAssertion":
            raise ValueError(f"Unclassified OWL axiom tag: {tag!r} -- add it to TBOX_TAGS or ABOX_TAGS")
    return {"predicates": predicates, "individuals": individuals, "tbox": tbox, "abox": abox}


def run_model(mmd_path: Path) -> dict:
    text = mmd_path.read_text()
    model = parse_dbt_diagram(text)
    shape = model_shape_stats(model)

    eps = eval_points_for(model)

    # Union sets across eval points, not sum-of-counts: the structural facts/
    # axioms (moments, histories, actions, succ, same_moment closure) are
    # identical every time since serialize() rebuilds from scratch per eval
    # point -- summing would count the same shared structure once per eval
    # point instead of once total.
    dl_union = {"facts": set(), "rules": set(), "predicates": set(), "constants": set()}
    owl_union = {"predicates": set(), "individuals": set(), "tbox": set(), "abox": set()}

    t0 = time.perf_counter()
    for emom, ehist, etgt in eps:
        model.evaluation_moment = emom
        model.evaluation_history = ehist
        model.target_proposition = etgt
        model.queries = []
        model = setup_layered_queries(model)
        serializer = DatalogIndexSerializer(model, evaluation_history=ehist, evaluation_moment=emom)
        program = serializer.serialize()
        serializer.evaluate()
        sets = datalog_line_sets(program)
        for k in dl_union:
            dl_union[k] |= sets[k]
    dl_time = time.perf_counter() - t0

    bin_path = konclude_path()
    if bin_path is None:
        raise RuntimeError("Konclude binary not found")
    adapter = KoncludeAdapter(bin_path)

    owl_time = 0.0
    for emom, ehist, etgt in eps:
        model.evaluation_moment = emom
        model.evaluation_history = ehist
        model.target_proposition = etgt
        model.queries = []
        model = setup_layered_queries(model)
        strategy = EquivFullCardinalityStrategy()
        serializer = OWLSerializer(model, evaluation_moment=emom, evaluation_history=ehist, strategy=strategy)
        t0 = time.perf_counter()
        owl_xml = serializer.serialize()
        serialize_dt = time.perf_counter() - t0
        sets = owl_axiom_sets(owl_xml)
        for k in owl_union:
            owl_union[k] |= sets[k]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".owl", delete=False) as f:
            f.write(owl_xml)
            temp_path = Path(f.name)
        try:
            result = adapter.run(temp_path, ReasoningMode.REALISATION,
                                  timeout=KONCLUDE_TIMEOUT, verbose=False)
            if not result.success:
                raise RuntimeError(f"Konclude failed on {mmd_path.name} @ ({emom},{ehist},{etgt}): {result.error_message}")
            owl_time += serialize_dt + result.wall_clock_time
        finally:
            temp_path.unlink()

    n_eps = len(eps)
    return {
        "name": mmd_path.stem,
        "shape": shape,
        "datalog": {k: len(v) for k, v in dl_union.items()},
        "owl": {k: len(v) for k, v in owl_union.items()},
        "datalog_time": dl_time / n_eps,
        "owl_time": owl_time / n_eps,
    }


def write_table_models(rows, path: Path):
    lines = [
        r"% Auto-generated by generate_tables.py -- do not edit by hand",
        r"\begin{tabular}{l r r r r r r}",
        r"\hline",
        r"Model & Moments & Hist. & Depth & Agents & Actions & Eval pts \\",
        r" & & & & total (max/mom.) & total (max/mom.) & actual (max poss.) \\",
        r"\hline",
    ]
    for r in rows:
        s = r["shape"]
        lines.append(
            f"{tex_escape(r['name'])} & {s['moments']} & {s['histories']} & {s['depth']} & "
            f"{s['agents_total']} ({s['agents_max']}) & {s['actions_total']} ({s['actions_max']}) & "
            f"{s['eval_points_actual']} ({s['eval_points_max']}) \\\\"
        )
    lines += [r"\hline", r"\end{tabular}", ""]
    path.write_text("\n".join(lines))


def write_table_translations(rows, path: Path):
    lines = [
        r"% Auto-generated by generate_tables.py -- do not edit by hand",
        r"\begin{tabular}{l r r r r r r r r r r}",
        r"\hline",
        r"Model & \multicolumn{5}{c}{pyDatalog} & \multicolumn{5}{c}{OWL / Konclude} \\",
        r" & Vocab & Const. & Facts & Rules & Avg.\ time (s) & Vocab & Indiv. & ABox & TBox & Avg.\ time (s) \\",
        r"\hline",
    ]
    for r in rows:
        d, o = r["datalog"], r["owl"]
        lines.append(
            f"{tex_escape(r['name'])} & {d['predicates']} & {d['constants']} & {d['facts']} & {d['rules']} & {r['datalog_time']:.3f} & "
            f"{o['predicates']} & {o['individuals']} & {o['abox']} & {o['tbox']} & {r['owl_time']:.3f} \\\\"
        )
    lines += [r"\hline", r"\end{tabular}", ""]
    path.write_text("\n".join(lines))


def main():
    mmd_files = sorted(MODELS_DIR.glob("*.mmd"))
    rows = []
    for mmd_path in mmd_files:
        print(f"Analyzing {mmd_path.name}...", file=sys.stderr)
        rows.append(run_model(mmd_path))

    write_table_models(rows, OUT_DIR / "table_models.tex")
    write_table_translations(rows, OUT_DIR / "table_translations.tex")
    print(f"Wrote 2 tables to {OUT_DIR}", file=sys.stderr)


if __name__ == "__main__":
    main()
