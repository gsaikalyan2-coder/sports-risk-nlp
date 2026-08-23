"""Phase 20 -- the Streamlit shell. A renderer, and deliberately nothing else.

Every number, every label and every guard in this file comes from
`src.dashboard`, which is pure Python, imports no ML stack, and is covered by
`tests/test_dashboard.py`. `notebooks/01_eda.ipynb` is the precedent: a thin
viewer over tested functions. Business logic does not live in the file the
Streamlit runtime executes, because a property enforced inside a Streamlit
callback is a property no test can assert -- and this project has now found the
same "the check and the thing it protects were related by assumption" defect in
three consecutive phases.

`tests/test_dashboard.py` enforces that structurally: this module may import from
`src.dashboard` and from nowhere else under `src.`, and may not construct a
`DashboardView`, `ExplanationCard` or `CardSet` itself.

Run:  streamlit run dashboard/app.py
      docker compose up dashboard      (light image, no torch -- see backend.py)
"""

from __future__ import annotations

import streamlit as st

from src.dashboard import (
    LexiconBackend,
    build_view,
    construct_contribution_chart,
    construct_probability_chart,
    known_examples,
    risk_meter,
)

st.set_page_config(page_title="Pre-competition construct profiling", layout="wide")


@st.cache_resource
def _replay():
    return known_examples()


@st.cache_resource
def _lexicon():
    return LexiconBackend()


def _svg(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def _render(view) -> None:
    st.caption(f"Source — {view.source}")
    st.warning(view.caveat)

    # The stamp is rendered *outside* the expander below and above the fold,
    # because a stamp inside a collapsed expander is present in the DOM and
    # absent from the screen -- and from every screenshot that becomes a paper
    # figure. "It renders" is not "a reader sees it"; that distinction is the
    # whole reason this phase strengthened its gate.
    st.caption(view.risk.stamp)
    _svg(risk_meter(view.risk))

    # surfaces[0] is the risk index, already drawn as the meter above; repeating
    # it as a tile made the same number appear twice on one screen.
    tiles = [s for s in view.surfaces if s is not view.risk]
    columns = st.columns(len(tiles))
    for column, surface in zip(columns, tiles, strict=False):
        with column:
            st.metric(surface.label, surface.display)
            st.caption(surface.detail)

    st.info(
        "The fusion layer decomposes risk over ten constructs, of which six carry a "
        "fixed direction under the default conservative policy; the remaining four "
        "are detected and displayed but do not move the index unless an "
        "interpretation direction is resolved."
    )

    left, right = st.columns(2)
    with left:
        _svg(construct_contribution_chart(view.bars))
    with right:
        _svg(construct_probability_chart(view.bars))
    st.caption(f"Bar scale — {view.scale_label}")

    st.subheader("Span → construct → risk")
    if view.exportable:
        st.markdown(view.export_markdown())
    else:
        for bar in view.bars:
            if not bar.detected:
                continue
            spans = (
                ", ".join(f"`{s.text}`" for s in bar.spans) if bar.spans else "_no supporting span_"
            )
            st.markdown(f"**{bar.construct}** — {bar.note} — {spans}")

    if view.unevidenced_driver_count:
        st.error(
            f"{view.unevidenced_driver_count} construct(s) moved the risk index with no "
            "supporting text span. The model is asserting something it cannot point at. "
            "Corpus-wide this is 104 of 120 driver rows (86.7%), reported rather than hidden."
        )

    with st.expander("Provenance and limitations — read before quoting any number"):
        for notice in view.notices:
            st.markdown(f"- {notice}")
        st.markdown(f"- {view.card.provenance}")
        st.markdown(f"- {view.card.risk.provenance}")
        st.markdown(f"**{view.risk.stamp}**")


st.title("Pre-competition psychological construct profiling")
st.markdown(
    "Research and decision-support only. Not a clinical instrument, and no "
    "individual-level claim about any identifiable person. Every number below is "
    "agreement with labels this project's own generator planted in synthetic text."
)

tab_known, tab_live = st.tabs(["Known examples (reproducible)", "Score your own text"])

with tab_known:
    replay = _replay()
    choice = st.selectbox("Committed known example", replay.example_ids)
    st.markdown(f"> {replay.get(choice).text}")
    _render(build_view(example_id=choice, backend=replay))

with tab_live:
    st.markdown(
        "Paste any text. It is scored by the lexicon baseline in this browser session, "
        "shown back to you, and then forgotten — nothing is stored, logged or cached."
    )
    pasted = st.text_area("Text", height=140, placeholder="Type or paste a few sentences…")
    if pasted.strip():
        st.markdown(f"> {pasted}")
        _render(build_view(text=pasted, backend=_lexicon()))
    else:
        st.caption("Waiting for text.")
