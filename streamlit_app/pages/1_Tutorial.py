import streamlit as st

st.set_page_config(page_title="Help — ALOn Model Explorer", page_icon="❓", layout="wide")

st.title("Help")

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

    If we conjoin the above fragments we can pop it into the "model definition" box and see a rendering of our model.
    """)

