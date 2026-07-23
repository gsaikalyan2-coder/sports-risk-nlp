import streamlit as st

st.set_page_config(page_title="Athlete Psych Risk Profiler", layout="wide")
st.title("Pre-Competition Psychological Risk Profiler")
st.caption("Research / decision-support demo. Not a diagnostic tool.")

text = st.text_area("Paste pre-competition athlete text:", height=160)
if st.button("Analyze") and text.strip():
    st.info("Wire up src.models + src.risk here (Phase 20).")
    # TODO: construct probabilities -> risk index -> highlighted spans
