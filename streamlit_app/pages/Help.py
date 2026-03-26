import streamlit as st

st.set_page_config(page_title="Help — ALOn Model Explorer", page_icon="❓", layout="wide")

st.title("Help")

st.markdown("""
This Streamlit app provides a very minimal IDE for editing and reasoning over ALOn (Action Logic with Opposing (for n agents)) models.
You can use the Streamlit Community Cloud [hosted](https://alon-model-checker.streamlit.app/) version (it might take a while to "warm up") or you can run it on [localhost](https://github.com/bparsia/alon-streamlit-app/). If you do the latter, you can run the [Konclude](https://konclude.com)
based model checker. (As of March 2026, there's no huge advantage to that unless you're going to look at the OWL output (e.g., in Protege) or want to play with
weird propositions.) Otherwise, the system uses [pyDatalog](https://sites.google.com/site/pydatalog/). (Yes, pyDatalog is mothballed, but it works fine and is pure Python which made 
Streamlit Cloud deployment easier.)

## Input syntax
We abuse Mermaid class diagrams to specify ALOn Models. While you can edit models on this page, it's not a super awesome experience. Using the free [Mermaid live editor](https://mermaid.live/edit) is a much nicer experience.

There are two structural approaches you can use for your model specs: One based on discrete branching time (DBT) structures and one based on "indicies" (which are closer to what we translate too; these use a more traditional relational semantics where each world represents a moment/history pair).

### A trivial, single agent, scenario

Let's suppose we are trying to capture a scenario where we have one agent, Alice, and she can either `shoot Dan` or `stand still`. The state of interest is whether Dan is alive or dead.

We need to specify some stuff before getting to the model structure. This is done in the "header" of the diagram (using a YAML dialect):

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

The header is bracked by `---` each on it's own line. You can add a title. `type` is either `DBT` or `index`.

Agents are represented by positive integers. For each agent you need to enumerate the "agent types" available to that agent.

You can also (optionally) add informative aliases for agents, action types, and propositions but currently these are just for the reader.

""")
