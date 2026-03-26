import sys
from pathlib import Path
import streamlit as st
from streamlit_mermaid import st_mermaid

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from alo_translator.parsers.dbt_parser import parse_dbt_diagram
from utils import (
    copy_button,
    format_model_overview,
    format_history_table_md,
    format_results_table,
    run_analysis_datalog,
)

st.set_page_config(page_title="Tutorial — ALOn Model Explorer", page_icon="📖", layout="wide")

st.title("Tutorial")

# ---------------------------------------------------------------------------
# The example model used throughout this page
# ---------------------------------------------------------------------------

TUTORIAL_MODEL = """\
---
title: Trivial 1 agent case
type: DBT
actions:
  1:
    - sd
    - ss
aliases:
  1: Alice
  sd: shoots Dan
  ss: stands still
  q: Dan dies
result: q
evaluation_point: m/h1
---
classDiagram
direction BT
  m --> m1 : h1({sd1})
  m --> m2 : h2({ss1})
  m1: q
  m2: ~q
"""

st.markdown("""## ALOn Causal Model basics

For a "single step" model, i.e., when we are evaluating the effects of actions at a moment on
possible next moments, we need to know which scenario we are considering. A causal scenario
consists of:

1. A set of agents, each with a set of available actions
2. A "moment" where those agents might perform some combination of the available actions
3. Possible histories corresponding to different sets of actions the agents did

By convention, the moment/history pair `m/h1` is where we evaluate responsibility. We need
alternative histories (`m/h2`, `m/h3`, …) to determine what *would* have happened if the agents
had acted otherwise. So a scenario specification must detail a possible history for each
"complete" set of actions.""")


with st.expander("A trivial, single agent, scenario", expanded=False):
    st.markdown("""
Let's suppose we have one agent, Alice, who can either `shoot Dan` or `stand still`. The
outcome of interest is whether Dan is alive or dead.

We need to specify some metadata before the temporal structure. This is done in a YAML header:

```yaml
---
title: Trivial 1 agent case
type: DBT
actions:
  1:
    - sd
    - ss
aliases:
  1: Alice
  sd: shoots Dan
  ss: stands still
  q: Dan dies
---
```

The header is bracketed by `---` on its own line. `type` is either `DBT` or `Index`.
Agents are represented by positive integers; for each you enumerate their available action types.
Aliases are optional human-readable labels for agents, action types, and propositions.

After the closing `---`, you specify the temporal structure as a Mermaid class diagram:

```
classDiagram
direction BT
  m --> m1 : h1({sd1})
  m --> m2 : h2({ss1})
  m1: q
  m2: ~q
```

Direction `BT` (bottom to top) reflects the traditional formatting of DBT structures.
Transitions carry a label with the history name and the complete group action for that successor.
Propositions true at a moment are written as "instance variables" on the moment node.

Note that action names are of the form `actiontype` + `agentnumber`, so `sd1` means
Alice shoots Dan. A second agent Beth (`2`) doing the same action would be `sd2`.
""")


# ---------------------------------------------------------------------------
# Static model display
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("The example model")

col_spec, col_diagram = st.columns([1, 2])

with col_spec:
    st.markdown("**Model specification**")
    st.code(TUTORIAL_MODEL, language="yaml")

with col_diagram:
    st.markdown("**Mermaid diagram**")
    st_mermaid(TUTORIAL_MODEL, height=400)

# Parse once for overview and analysis
model, partial_spec = parse_dbt_diagram(TUTORIAL_MODEL)

st.markdown(format_model_overview(model))


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("Run the analysis")
st.markdown(
    "Click below to evaluate responsibility at `m/h1` "
    "(Alice shoots Dan, Dan dies)."
)

if st.button("▶️ Run Analysis"):
    with st.spinner("Running…"):
        result_prop  = partial_spec.get("result", "q")
        eval_point   = partial_spec.get("evaluation_point", "m/h1")
        eval_history = eval_point.split("/")[1] if "/" in eval_point else "h1"

        satisfied = run_analysis_datalog(model, result_prop, eval_history)

        if satisfied is not None:
            results_md = format_results_table(model, satisfied, result_prop)
            col_r, col_rb = st.columns([8, 1])
            with col_r:
                st.markdown(results_md)
            with col_rb:
                copy_button(results_md, "📋 Copy")
