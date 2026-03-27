import sys
from pathlib import Path
import streamlit as st
from streamlit_mermaid import st_mermaid

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from alo_translator.parsers.dbt_parser import parse_dbt_diagram
from utils import (
    analysis_button,
    copy_button,
    format_model_overview,
    format_history_table_md,
    format_results_table,
    run_analysis_datalog,
)

st.set_page_config(page_title="Tutorial — ALOn Model Explorer", page_icon="📖")

st.title("Tutorial")

st.markdown("""# ALOn Causal Model basics

For a "single step" model, i.e., when we are evaluating the effects of actions at a moment on possible next moments. We need to know which scenario we are considering. A casudsl scenario consists of:

1. a set of agents each with a set of available actions
2. a "moment" where those agents might do some combinations of the available actions
3. possible histories which correspond to different sets of actions those agents did

By convention, the moment/history pair, `m/h1` is where we are evaluating responsibility. We need alternative histories (`m/h2`, `m/h3`) to determine what *would* have happend if the agents had acted otherwise. So a "scenario" specification needs to detail a possible histor for each "complete" set of actions.""")


with st.expander("A trivial, single agent, scenario", expanded=False):
    st.markdown("""
    Let's suppose we are trying to capture a scenario where we have one agent, Alice, and she can either `shoot Dan` or `stand still`. The outcome of interest is whether Dan is alive or dead.

    We need to specify some stuff before getting to the temporal structure. This is done in the "header" of the diagram (using a YAML dialect):

    ``` yaml
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

    The header is bracketed by `---` each on it's own line. You can add a title and other metadata. `type` is either `DBT` or `Index`.

    Agents are represented by positive integers. For each agent you need to enumerate the "agent types" available to that agent.

    You can also (optionally) add informative aliases for agents, action types, and propositions but currently these are just for the reader.

    After the closing `---`, you specify the temporal  structure as a Mermaid class diagram:

    ``` mermaid
    classDiagram
    direction BT
      m --> m1 : h1({sd1})
      m --> m2 : h2({ss1})
      m1: q
      m2: ~q
    ```

    Mermaid class diagrams are very flexible. We recommend that the direction be set to `BT` (bottom to top) to reflect traditional formatting of DBT structures in papers. The convention for DBT diagrams is that transitions between moments are represented with labels indicating the history name and the complete group action leading to that successor. Propositions true at a moment are represented by "instance variables."

    There's lots of ways to write a class diagram in Mermaid, but sticking to this style is best for our poor parser. Please note that actual action names are of the form `actiontypeagentnumber`. Thus `sd1` is `Alice shoots Dan`. If we had another agent, Beth, who was represeted by 2, then `sd2` would mean `Beth shoots Dan`.

    If we conjoin the above fragments we can pop it into the "model definition" box and see a rendering of our model.""")

    col_spec, col_diagram = st.columns([1, 2])
    MODEL_1 ="""---
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
classDiagram
direction BT
  m --> m1 : h1({sd1})
  m --> m2 : h2({ss1})
  m1: q
  m2: ~q 
"""
    with col_spec:
        st.markdown("**Model specification**")
        st.code(MODEL_1, language="yaml")

    with col_diagram:
        st.markdown("**Mermaid diagram**")
        st.image('streamlit_app/pages/images/tut1.png')

    # Parse once for overview and analysis
    model, partial_spec = parse_dbt_diagram(MODEL_1)

    st.markdown(
        """At this point we can run a complete responsibility analysis at `m/h1`. That is, for every possible "actor" (individual agent or group), we determine if that actor is potentially responsible (`pres`), strongly responsible (`sres`), or plainly responsible (`res`). We also determine whether the actor sees to it that the outcome happens (`dxstit`) and whether thier action is an actual cause of the outcome (either as a but for cause or a NESS (necessary element of a sufficient set) cause).
        
Click the button to see the results. A tick means the corresponding formula is true at `m/h1` and a blank means that it is false there."""
    )

    analysis_button("tut_analysis_1", model, partial_spec)

    st.markdown(
        """In this case, as is not surprising, Alice is every kind of responsible for Dan's death. If you tweak the model so Dan dies at `m2` (`m2: q`), then Alice will have no causal role in Dan's death as it would have happened no matter what she does, of her available actions"""
    )
    MODEL_2 = """---
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
classDiagram
direction BT
  m --> m1 : h1({sd1})
  m --> m2 : h2({ss1})
  m1: q
  m2: q
"""
    model2, partial_spec2 = parse_dbt_diagram(MODEL_2)
    analysis_button(
        "tut_analysis_2", model2, partial_spec2,
        label="▶️ Run Analysis on a model where Dan is doomed no matter what Alice does.",
    show_legend=False)

with st.expander("Shortcuts", expanded=False):
    st.markdown("""In order to have a model of the right sort and consistent with the semantics of ALOn, we must have one history for each "complete group action" that is for each possible combination of 1 action per agent. That is, we must enumerate the cross product of sets of available actions for agents. E.g., 2 agents with 2 actions each require 4 histories. Adding another agent with 2 actions takes you to 8 and so on.

The key information from a history is whether or not the outcome of interest holds. Since this is (in current models) just whether a proposition or its negation holds, we take advantage of that and allow the modeller to omit histories where the negation holds. Thus the following spec is equivalent to our original model:

```
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
classDiagram
direction BT
  m --> m1 : h1({sd1})
  m1: q
```

This will produce the exact same responsibility analysis as the complete spec.

(In future implementations, we may support designating the default rule in case it'd be more efficient to default to the positive proposition.) Several of the example models are partial models.
""")

MODEL_3 = """---
title: Example 3.5
type: DBT
actions:
  1:
    - sd
    - ss
  2:
    - ss
    - ha
opposings:
  sd1:
    - ha2
aliases:
  1: Alice
  2: Beth
  sd: shoots Dan
  ss: stands still
  ha: hits Alice
  q: Dan dies
---
classDiagram
direction BT
  m --> m1 : h1({sd1, ss2})
  m1: q"""
with st.expander("An example with opposing", expanded=False):
    st.markdown(f"""While the trivial, 1 agent examples suffices to show that there is meaningful responsibility attribute even for a single agent, the interesting scenarios for ALOn is where there are multiple agents acting in concert or in opposition. We can thus extend our initial model to example 3.5 from Where Responsibility Takes You:
     
```
{MODEL_3}
```  
(Note, since in all other histories Dan doesn't die, we just specify `h1`.)

In addition to adding a second agent (2, aka, "Beth") and an additional action type (`ha` aka "hits Alice"), we add an opposing relation between *Beth's* hitting Alice and *Alice's* shooting Dan. 

Note that not all action types are available to all agents: We don't model Beth's shooting Dan or Alice hitting herself. This is the modeller's choice!""")
    model3, partial_spec3 = parse_dbt_diagram(MODEL_3)
    analysis_button(
        "tut_analysis_3", model3, partial_spec3,
        label="▶️ Run Analysis on a example 3.5.",
    show_legend=False)
    st.markdown("""If you run the analysis, you'll find that the results are the same as presented in "[Where Responsibility Takes You](https://link.springer.com/book/10.1007/978-3-031-17111-6)" on page 58:""")
    st.image('streamlit_app/pages/images/3.5results.png')
    st.markdown("""(We don't show all the lower level queries in our standard table. You can test fairly arbitrary formulae using the underlying toolkit.)
    
One point to note is that our responsibility analysis is *complete* that is we test all the causation and responsibility queries for *all* relevant actions and actors. Thus when look the book results, we do not see any analysis of the group of Alice and Beth or their joint action of (Alice) shooting Dan *and* (Beth) standing still. Interestingly, the group of Alice and Beth is *at least* as responsible as Alice is alone, but also while the group sees to it that Dan dies, Alice alone does not. This teases out the way that Beth's omission is causally relevant: She's didn't cause Dan's death, but she and Alice together did.""")


with st.expander("Next Steps", expanded=False):
    st.markdown("""You're now ready to explore! There are several pre-defined models you can load from the menu in the sidebar including all 4 examples from chapter 3 in "Where Responsibility Takes You". If you come up with other intereting models, please submit them for sharing.
""")