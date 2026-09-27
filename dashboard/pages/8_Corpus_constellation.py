"""Page 8 -- the whole corpus on one screen. A renderer over a committed artifact.

Same contract as every other page: only `src.dashboard` is reachable, nothing is
constructed here, and the stamp is above the fold and outside anything
collapsible.

Three things are specific to this page.

**Nothing is computed while the reader looks at it.** The numbers come from
`reports/corpus_cloud.json`, built offline by `scripts/build_corpus_cloud.py`.
Scoring 4,000 records takes about three minutes, which is not a page load, and a
cached three-minute computation would be a stale cache nobody can date.

**A missing artifact is a message, not a traceback.** `load_cloud` raises
`CorpusCloudMissing` carrying the rebuild command. A fresh clone has no
`data/raw/` and may have no artifact either, and the honest response is to say
which command produces it.

**The four rows sitting on the midpoint are explained on the page.** They are the
conservative default working as designed -- four signals whose direction is left
open cannot move an index -- and a reader who is not told that reads four flat rows
as four broken ones.

Run:  streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Corpus constellation", layout="wide")

from src.dashboard import (  # noqa: E402
    CorpusCloudMissing,
    corpus_cloud_chart,
    load_cloud,
    plain,
    theme,
)

mode = st.session_state.get("mode", theme.DEFAULT_MODE)
st.markdown(theme.app_css(mode), unsafe_allow_html=True)

st.markdown('<p class="mono-label">Corpus</p>', unsafe_allow_html=True)
st.markdown(f"# {plain.CLOUD_TITLE}")
st.markdown(theme.lede(plain.CLOUD_PLAIN), unsafe_allow_html=True)

try:
    cloud = load_cloud()
except CorpusCloudMissing as missing:
    st.warning(str(missing))
    st.stop()

# Above the fold, outside anything collapsible.
st.caption(cloud.stamp)
st.caption(cloud.scale_label)

for column, surface in zip(st.columns(len(cloud.surfaces)), cloud.surfaces, strict=True):
    with column:
        st.markdown(
            f'<div class="widget"><span class="wl">{surface.label}</span>'
            f'<span class="wv">{surface.display}</span>'
            f'<span class="wu">{surface.detail}</span></div>',
            unsafe_allow_html=True,
        )

st.markdown(corpus_cloud_chart(cloud), unsafe_allow_html=True)

st.markdown("## How to read it")
for heading, body in plain.CLOUD_HOW_TO_READ:
    st.markdown(f"**{heading}.** {body}")

st.info(plain.CLOUD_MIDPOINT_NOTE)
st.info(plain.CLOUD_SILENT_NOTE)

st.markdown("## Row by row")
for lane in cloud.lanes:
    middle = lane.median.display if lane.median else "no middle to report"
    st.markdown(
        f"**{lane.plain_name}** &mdash; {lane.n_planted} records planted, "
        f"{lane.n_scored} scored, middle {middle}"
    )

with st.expander("Provenance and limitations: read before quoting any number"):
    st.markdown(f"- {plain.CLOUD_WHAT_IT_IS_NOT}")
    st.markdown(f"- {plain.CLOUD_SOURCE_NOTE}")
    st.markdown(f"- {cloud.sample_note}")
    st.markdown(f"- Scored under: {cloud.policy}, by the {cloud.backend} reader")
    st.markdown(f"- {cloud.caveat}")
    st.markdown(f"- {cloud.provenance}")
    st.markdown(f"**{cloud.stamp}**")
