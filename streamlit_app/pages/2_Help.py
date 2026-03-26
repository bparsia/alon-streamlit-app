import streamlit as st

st.set_page_config(page_title="Help — ALOn Model Explorer", page_icon="❓", layout="wide")

st.title("Help")

st.markdown("""
This Streamlit app provides a very minimal IDE for editing and reasoning over ALOn (Action Logic with Opposing (for n agents)) models.
You can use the Streamlit Community Cloud [hosted](https://alon-model-checker.streamlit.app/) version (it might take a while to "warm up") or you can run it on [localhost](https://github.com/bparsia/alon-streamlit-app/). If you do the latter, you can run the [Konclude](https://konclude.com)
based model checker. (As of March 2026, there's no huge advantage to that unless you're going to look at the OWL output (e.g., in Protege) or want to play with
weird propositions.) Otherwise, the system uses [pyDatalog](https://sites.google.com/site/pydatalog/). (Yes, pyDatalog is mothballed, but it works fine and is pure Python which made 
Streamlit Cloud deployment easier.)

# Models

# Input syntax
We abuse Mermaid class diagrams to specify ALOn Models. While you can edit models on this page, it's not a super awesome experience. Using the free [Mermaid live editor](https://mermaid.live/edit) is a much nicer experience.

There are two structural approaches you can use for your model specs: One based on discrete branching time (DBT) structures and one based on "indicies" (which are closer to what we translate too; these use a more traditional relational semantics where each world represents a moment/history pair).

""")
