import streamlit as st

st.set_page_config(page_title="Help — ALOn Model Explorer", page_icon="❓", layout="wide")

st.title("Help")

st.markdown("""
This Streamlit app provides a very minimal IDE for editing and reasoning over ALOn (Action Logic with Opposing (for n agents)) models.
You can use the Streamlit Community Cloud hosted version or you can run it on localhost. If you do the latter, you can run the Konclude
based model checker. (As of March 2026, there's no huge advantage to that unless you're going to look at the OWL output or want to play with
weird propositions.) Otherwise, the system uses pyDatalog. (Yes, pyDatalog is mothballed, but it works fine and is pure Python which made 
Streamlit Cloud deployment easier.)

## Input syntax


""")
