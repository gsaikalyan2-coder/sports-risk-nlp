"""The design system, as tokens. One source for the shell, the panels and the figures.

Why a module and not three stylesheets
--------------------------------------
The dashboard paints on three surfaces that cannot share a stylesheet: Streamlit
widgets (CSS injected into the host page), the animated panels (CSS inside an
iframe), and the SVG figures (attributes baked into markup). Before this module
each carried its own copy of the palette, and a palette in three places is a
palette that drifts -- the legend swatches on the panel were still the old hues
two phases after the bars had changed.

So the tokens live here, once, and each surface renders them into whatever form
it needs. `DESIGNcohere.md` at the repository root is the specification; this
file is its executable half, and the token names match it deliberately so a
reader can hold the two side by side.

Nothing here is load-bearing for honesty. Sign is encoded by position in
`charts.py`, inertness by hatch, dash and the literal word, and every caption
comes from `copy.py`. Delete this module and the page would be ugly and say
exactly the same things.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------

CANVAS = "#ffffff"
PRIMARY = "#17171c"
COHERE_BLACK = "#000000"
INK = "#212121"
DEEP_GREEN = "#003c33"
DARK_NAVY = "#071829"
SOFT_STONE = "#eeece7"
PALE_GREEN = "#edfce9"
PALE_BLUE = "#f1f5ff"
HAIRLINE = "#d9d9dd"
BORDER_LIGHT = "#e5e7eb"
CARD_BORDER = "#f2f2f2"
MUTED = "#93939f"
SLATE = "#75758a"
BODY_MUTED = "#616161"
ACTION_BLUE = "#1863dc"
FOCUS_BLUE = "#4c6ee6"
CORAL = "#ff7759"
CORAL_SOFT = "#ffad9b"
FORM_FOCUS = "#9b60aa"
ON_DARK = "#ffffff"

#: The diverging pair for every signed mark in `charts.py`.
#:
#: Coral raises, deep green lowers. Chosen over any other pair in the system for
#: one reason that is not aesthetic: their *lightness* differs by roughly 45
#: points, so the two survive a grayscale print and a colour-vision deficiency.
#: `PROJECT_PLAN.md` Phase 24 gates on grayscale legibility, and a pair that
#: failed it would fail after the figures were drawn. Sign is still carried by
#: position; hue is the redundant second channel, as it has always been.
RAISES = CORAL
LOWERS = DEEP_GREEN
SEQUENTIAL = DEEP_GREEN

# ---------------------------------------------------------------------------
# Type
# ---------------------------------------------------------------------------

#: The proprietary faces are not bundled (`DESIGNcohere.md`, Known Gaps), so the
#: documented fallbacks are the implementation: Space Grotesk for the display
#: tier, Inter for UI, a monospace stack for technical labels.
FONT_DISPLAY = '"Space Grotesk", Inter, ui-sans-serif, system-ui, sans-serif'
FONT_UI = "Inter, Arial, ui-sans-serif, system-ui, sans-serif"
FONT_MONO = '"IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace'

GOOGLE_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    "family=Inter:wght@400;500&family=Space+Grotesk:wght@400;500&"
    'family=IBM+Plex+Mono:wght@400;500&display=swap">'
)

#: SVG attribute form of the UI stack. The figures carry no font file, so a
#: missing webfont changes metrics, never layout.
FONT_SVG = f'font-family="{FONT_UI}"'
FONT_SVG_MONO = f'font-family="{FONT_MONO}"'

# ---------------------------------------------------------------------------
# Shape and rhythm
# ---------------------------------------------------------------------------

RADIUS_XS = "4px"
RADIUS_SM = "8px"
RADIUS_MD = "16px"
RADIUS_LG = "22px"
RADIUS_XL = "30px"
RADIUS_PILL = "32px"

SPACE_XS = "6px"
SPACE_SM = "8px"
SPACE_MD = "12px"
SPACE_LG = "16px"
SPACE_XL = "24px"
SPACE_XXL = "32px"
SPACE_SECTION = "80px"


# ---------------------------------------------------------------------------
# Light and dark, as two sets of the same token names
# ---------------------------------------------------------------------------
#
# The dashboard offers both. `DESIGNcohere.md` is a two-polarity system already
# -- white editorial canvas, deep green and dark navy product bands -- so dark
# mode is not an invention here: it promotes the documented product band to the
# page floor and inverts the text roles that go with it.
#
# Both palettes define *every* name. That is the point: a mode that filled in
# only the colours it wanted to change would leave the rest at light values and
# produce the classic failure -- dark background, dark text, unreadable page.

LIGHT: dict[str, str] = {
    "canvas": CANVAS,
    "surface": CANVAS,
    "surface-alt": SOFT_STONE,
    "band": DEEP_GREEN,
    "on-band": ON_DARK,
    "ink": INK,
    "body": BODY_MUTED,
    "muted": MUTED,
    "slate": SLATE,
    "hairline": HAIRLINE,
    "border": BORDER_LIGHT,
    "card-border": CARD_BORDER,
    "button": PRIMARY,
    "on-button": ON_DARK,
    "link": ACTION_BLUE,
    "accent": CORAL,
    "figure-surface": CANVAS,
}

DARK: dict[str, str] = {
    "canvas": "#0b1420",  # a shade under dark-navy, so bands still read
    "surface": DARK_NAVY,  # documented product-band navy, now the card
    "surface-alt": "#0f2233",
    "band": DEEP_GREEN,
    "on-band": ON_DARK,
    "ink": "#f4f4f2",
    "body": "#c6c8cd",
    "muted": "#9aa1ab",
    "slate": "#9aa1ab",
    "hairline": "#20364a",
    "border": "#20364a",
    "card-border": "#20364a",
    "button": CANVAS,  # the system flips CTA polarity on dark, not hue
    "on-button": INK,
    "link": "#7fb0ff",  # action blue lifted to hold contrast on navy
    "accent": CORAL,
    "figure-surface": CANVAS,  # figures stay light: they are printed media cards
}

MODES: dict[str, dict[str, str]] = {"light": LIGHT, "dark": DARK}
DEFAULT_MODE = "light"


def palette(mode: str) -> dict[str, str]:
    """The token set for a mode. Unknown modes fall back rather than half-paint."""
    return MODES.get(mode, MODES[DEFAULT_MODE])


#: The widget key the appearance radio uses, and the plain key the choice is
#: copied into. They must differ: Streamlit forbids assigning to a key a widget
#: owns, and the whole point of the plain key is that it is NOT a widget's.
APPEARANCE_WIDGET_KEY = "appearance_choice"
MODE_KEY = "mode"


def mode_control(st) -> str:
    """Render the light/dark control in the sidebar and return the chosen mode.

    Takes the Streamlit module as an argument rather than importing it, so this
    package stays importable with no Streamlit installed. Every test under
    `tests/test_dashboard*.py` relies on that, and a module-level
    `import streamlit` here would be the one import that broke it.

    Why a helper at all, when the radio is six lines
    ------------------------------------------------
    Before this, three of eleven pages offered the control and eight did not, so a
    reader who opened the brain atlas or the taxonomy deck first had no way to
    switch appearance at all: the page painted whatever `mode` happened to be in
    session state, with no visible cause and no way to change it. Copying the
    radio into eight more files would have put eleven copies of the widget key,
    the fallback and the write-back in the tree, and the failure that shape
    produces is one page seeding its index from a different key than it writes.

    Streamlit garbage-collects a widget's state when the widget is not rendered
    on the current page, so the radio's own key does NOT survive navigation. The
    choice is therefore copied into a plain (non-widget) key, which does persist,
    and the index is seeded from that key on every page. An unknown value in it
    falls back rather than raising, because session state outlives a rename.
    """
    modes = tuple(MODES)
    current = st.session_state.get(MODE_KEY, DEFAULT_MODE)
    if current not in modes:
        current = DEFAULT_MODE
    choice = st.sidebar.radio(
        "Appearance",
        modes,
        index=modes.index(current),
        format_func=str.capitalize,
        horizontal=True,
        key=APPEARANCE_WIDGET_KEY,
    )
    st.session_state[MODE_KEY] = choice
    return choice


#: The three Phase 26 pages, by the fragment Streamlit puts in their nav href.
COGNITIVE_PAGES: tuple[str, ...] = ("Brain_atlas", "Cognitive_load")

COGNITIVE_FLAG = "SRN_COGNITIVE_LAYER"


#: Values that turn the layer OFF. Anything else, including unset, leaves it on.
COGNITIVE_OFF_VALUES = frozenset({"0", "false", "no", "off"})


def cognitive_layer_enabled() -> bool:
    """Whether the Phase 26 pages are switched on for this process.

    ON BY DEFAULT. Unset means on; only an explicit off value turns it off.

    This is the reverse of how `.claude.md` section 11.3 wrote the flag, and the
    reversal was earned rather than convenient. While the layer was unbuilt, a
    default of off kept an unfinished stretch feature out of the way. Now that it
    is built and tested, a default of off means every route that misses one
    environment variable renders a dashboard with three pages silently missing --
    which is not a safe failure, it is an invisible one. It happened three times
    in a row: the shell `set` never reached the container, `.env` had no such
    line, and `docker compose restart` reuses a container without re-reading the
    compose file. In all three the app was correct and looked broken.

    Nothing about the layer's honesty depends on this default. The provenance
    stamps, the ethics gate in `src/biosignals/sources.py` and the activation
    screen in `neurovis.py` are enforced by construction and do not consult it.
    What the flag controls is visibility, and the safe direction for visibility
    is the one where a caveat-carrying page is present rather than absent.

    Read from the environment on every call rather than captured at import, so a
    test can flip it without reloading the module -- and so the answer cannot
    drift between the stylesheet that hides a nav link and the page that refuses
    to render, which are the two halves of the same rule.
    """
    return os.getenv(COGNITIVE_FLAG, "").strip().lower() not in COGNITIVE_OFF_VALUES


def _cognitive_nav_css() -> str:
    """Hide the Phase 26 nav entries unless the flag is set.

    Streamlit registers every file under `dashboard/pages/` unconditionally --
    there is no API for a conditional page -- so "the pages are not registered
    when the flag is unset" (`.claude.md` §11.3) is not achievable as written.
    Two halves are, and both are asserted:

      * this rule removes the entries from the menu, and
      * each page checks the flag and `st.stop()`s before its first `src.`
        import, so `src/biosignals` is genuinely never loaded.

    Hiding alone would leave the pages reachable by URL; stopping alone would
    leave three dead links in the menu. Neither half is sufficient, which is why
    neither is allowed to be the only one.
    """
    if cognitive_layer_enabled():
        return ""
    selectors = ",".join(f'[data-testid="stSidebarNav"] a[href*="{p}"]' for p in COGNITIVE_PAGES)
    return selectors + "{display:none}"


def app_css(mode: str = DEFAULT_MODE) -> str:
    """The Streamlit shell's stylesheet for one mode. Presentation only.

    Written as one string rather than assembled from the tokens above with an
    f-string per rule, because a stylesheet built by concatenation is one nobody
    reads. The token values are interpolated; the structure is literal.

    Returned dedented, and that is not cosmetic: `st.markdown` treats a
    four-space-indented block as a code fence, so an indented stylesheet renders
    as visible source text at the top of the page. Found by loading the app and
    looking at it -- the unit tests saw a perfectly good string.
    """
    p = palette(mode)
    css = f"""
    {GOOGLE_FONTS}
    <style>
      :root{{
        --canvas:{p["canvas"]}; --primary:{p["button"]}; --ink:{p["ink"]}; --deep-green:{p["band"]};
        --stone:{p["surface-alt"]}; --pale-green:{PALE_GREEN}; --pale-blue:{PALE_BLUE};
        --hairline:{p["hairline"]}; --border-light:{p["border"]}; --card-border:{p["card-border"]};
        --muted:{p["muted"]}; --slate:{p["slate"]}; --body-muted:{p["body"]};
        --blue:{p["link"]}; --coral:{p["accent"]}; --coral-soft:{CORAL_SOFT};
      }}
      html, body, .stApp, [class*="css"]{{
        font-family:{FONT_UI}; color:var(--ink); background:var(--canvas);
      }}
      .block-container{{padding-top:{SPACE_XXL}; padding-bottom:{SPACE_SECTION};
        max-width:1180px}}
      /* Streamlit paints the header and the sidebar from its own theme config,
         which is a single static file and cannot follow a runtime mode. Left
         alone, dark mode kept a white header and a cream sidebar -- visible only
         in the browser, and invisible to every test. */
      [data-testid="stHeader"]{{background:transparent}}
      [data-testid="stSidebar"]{{background:var(--stone);
        border-right:1px solid var(--hairline)}}
      [data-testid="stSidebar"] *{{color:var(--ink)}}

      /* Display tier. One oversized headline per page, then restrained UI copy. */
      h1{{font-family:{FONT_DISPLAY}!important; font-size:60px!important; font-weight:400!important;
        line-height:1!important; letter-spacing:-1.2px!important; color:var(--ink);
        margin:0 0 {SPACE_LG} 0!important}}
      h2{{font-family:{FONT_UI}!important; font-size:32px!important; font-weight:400!important;
        line-height:1.2!important; letter-spacing:-.32px!important;
        margin-top:{SPACE_SECTION}!important; margin-bottom:{SPACE_LG}!important}}
      h3{{font-size:24px!important; font-weight:400!important; line-height:1.3!important;
        letter-spacing:0!important}}
      p, li{{font-size:16px; line-height:1.5; color:var(--ink)}}
      .lede{{font-size:18px; line-height:1.4; max-width:68ch; color:var(--body-muted);
        margin-bottom:{SPACE_XL}}}

      /* Uppercase mono labels are the system's category and system markers. */
      .mono-label{{font-family:{FONT_MONO}; font-size:14px; letter-spacing:.28px;
        text-transform:uppercase; color:var(--slate)}}
      .micro{{font-size:12px; line-height:1.4; color:var(--muted)}}


      /* Widget tiles: warm stone product cards, 8px, flat -- no drop shadow.
         Fixed min-height and a flex column, so a tile with a two-line title is
         exactly as tall as one with a one-line title. Without it the grid's rows
         stagger, which reads as the tiles meaning different things. */
      [data-testid="stHorizontalBlock"]{{gap:{SPACE_XL}}}
      [data-testid="stColumn"] > div{{height:100%}}
      .widget{{background:var(--stone); border-radius:{RADIUS_SM};
        padding:{SPACE_XL}; min-height:232px; height:100%;
        display:flex; flex-direction:column; justify-content:space-between;
        transition:box-shadow .15s ease, border-color .15s ease}}
      .widget:hover{{box-shadow:inset 0 0 0 1px var(--hairline)}}
      .widget .wl{{min-height:34px}}
      .stButton{{margin:{SPACE_MD} 0 {SPACE_XL} 0}}

      /* The explanation page is reached by opening a tile, not from the menu.
         Hiding the entry keeps one route in and one meaning for "detail": the
         tile you clicked. `st.switch_page` is unaffected. */
      [data-testid="stSidebarNav"] a[href*="Signal_detail"]{{display:none}}
      {_cognitive_nav_css()}
      .widget.is-inert{{background:var(--canvas); border:1px solid var(--hairline)}}
      .widget .wl{{font-family:{FONT_MONO}; font-size:14px; letter-spacing:.28px;
        text-transform:uppercase; color:var(--slate); display:block;
        margin-bottom:{SPACE_MD}}}
      .widget .wv{{font-family:{FONT_DISPLAY}; font-size:48px; font-weight:400;
        line-height:1.2; letter-spacing:-.48px; color:var(--ink); display:block}}
      .widget .wu{{font-size:14px; line-height:1.4; color:var(--body-muted);
        display:block; margin-top:{SPACE_XS}}}
      .widget .wrule{{border:0; border-top:1px solid var(--hairline);
        margin:{SPACE_LG} 0 {SPACE_MD} 0}}

      /* The single hero number on the dashboard. Given more visual weight than
         a flat fill: a soft layered shadow and a hairline top edge so the card
         reads as raised rather than merely coloured-in. */
      .hero-figure{{background:var(--deep-green); color:{p["on-band"]};
        border-radius:{RADIUS_LG}; padding:{SPACE_XXL};
        box-shadow:0 1px 0 rgba(255,255,255,.08) inset, 0 12px 28px -16px rgba(0,0,0,.35);
        border:1px solid rgba(255,255,255,.06)}}
      .hero-figure .hv{{font-family:{FONT_DISPLAY}; font-size:72px; font-weight:400;
        line-height:1; letter-spacing:-1.44px; display:block; margin:8px 0}}
      .hero-figure .hl{{font-family:{FONT_MONO}; font-size:14px; letter-spacing:.28px;
        text-transform:uppercase; opacity:.8}}

      /* Band chip: filled rather than outlined, for more presence at a glance.
         Still taxonomy-chip geometry and still never a verdict on its own --
         only the fill treatment changed, not the meaning or the colour token. */
      .band{{display:inline-block; border:1px solid var(--coral);
        color:{ON_DARK}; background:var(--coral); border-radius:{RADIUS_XL};
        padding:6px 14px; font-size:14px; font-weight:500; line-height:1.71}}

      /* Buttons: near-black pill for the single primary action per surface,
         with a lift on hover so the primary action feels responsive. */
      .stButton > button{{background:var(--primary); color:{p["on-button"]};
        border:0; border-radius:{RADIUS_PILL}; padding:12px 24px; font-size:14px;
        font-weight:500; line-height:1.71; width:100%;
        transition:transform .12s ease, box-shadow .12s ease, opacity .12s ease}}
      /* Streamlit nests the label in its own <p>/<div>, which carries the theme's
         text colour and wins over the button rule. Without these two selectors the
         pill renders near-black on near-black -- invisible, and invisible only on
         the rendered page: the markup is correct either way. */
      .stButton > button p, .stButton > button div, .stButton > button span{{
        color:{p["on-button"]}!important; font-size:14px; font-weight:500}}
      .stButton > button:hover{{background:var(--primary); opacity:.88; color:{p["on-button"]};
        transform:translateY(-1px); box-shadow:0 6px 16px -8px rgba(0,0,0,.35)}}
      .stButton > button:hover p{{color:{p["on-button"]}!important}}
      .stButton > button:active{{transform:translateY(0)}}
      .stButton > button:focus{{box-shadow:0 0 0 3px {FOCUS_BLUE}55}}

      /* Inputs: rectangular, thin grey rule, violet focus border. Radius
         raised from 4px to match the tile/card radius elsewhere on the page
         instead of reading as a separate, sharper-edged system. */
      .stTextArea textarea, .stTextInput input{{background:var(--canvas);
        color:var(--ink); border:1px solid var(--hairline)!important;
        border-radius:{RADIUS_SM}!important; font-size:16px!important;
        padding:{SPACE_MD}!important; transition:border-color .12s ease}}
      .stTextArea textarea:focus, .stTextInput input:focus{{
        border-color:{FORM_FOCUS}!important; box-shadow:none!important}}
      div[data-baseweb="select"] > div{{background:var(--canvas)!important;
        border:1px solid var(--hairline)!important; border-radius:{RADIUS_SM}!important;
        color:var(--ink)!important; font-size:16px!important}}
      /* The select's fill sits on an emotion-classed div with no stable
         attribute of its own, painted from the static theme config -- so it is
         addressed through the widget's testid and not through baseweb. Checked
         in the browser: a narrower selector matched nothing and dark mode kept a
         cream dropdown. */
      [data-testid="stSelectbox"] div{{background-color:var(--canvas)!important}}
      [data-testid="stSelectbox"] *{{color:var(--ink)!important}}
      [data-testid="stSelectbox"] svg{{fill:var(--ink)!important}}
      /* The list the select DROPS is portalled to <body>, outside the widget's
         own testid, so every rule above stops at the closed control. In dark
         mode that meant a navy select opening a white sheet of light-ink options
         over a dark page. Found with the list open in a browser: a screenshot of
         the closed control, and every unit test, passes either way. */
      [data-testid="stSelectboxVirtualDropdown"]{{background:var(--canvas)!important;
        border:1px solid var(--hairline)!important}}
      [data-testid="stSelectboxVirtualDropdown"] *{{color:var(--ink)!important}}
      [data-testid="stSelectboxVirtualDropdown"] [role="option"]{{
        background:var(--canvas)!important}}
      [data-testid="stSelectboxVirtualDropdown"] [role="option"]:hover,
      [data-testid="stSelectboxVirtualDropdown"] [aria-selected="true"]{{
        background:var(--stone)!important}}
      /* Streamlit's own running indicator is painted from the static theme
         config, whose textColor is the light-mode ink, so "Running" and "Stop"
         were ink-on-ink for the seconds a dark page was rerunning. */
      [data-testid="stStatusWidget"], [data-testid="stStatusWidget"] *{{
        color:var(--ink)!important; fill:var(--ink)!important}}
      [data-baseweb="tooltip"], [data-baseweb="tooltip"] *{{
        background:var(--stone)!important; color:var(--ink)!important}}
      label p{{font-size:14px!important; color:var(--body-muted)!important}}

      /* Rule-separated rows and quiet containers, not boxes everywhere. */
      blockquote{{border-left:2px solid var(--ink)!important; background:transparent;
        padding:{SPACE_SM} 0 {SPACE_SM} {SPACE_XL}!important; margin:{SPACE_LG} 0!important}}
      blockquote p{{font-size:18px!important; line-height:1.4}}
      div[data-testid="stExpander"]{{border:1px solid var(--hairline);
        border-radius:{RADIUS_SM}; background:var(--canvas)}}
      div[data-testid="stExpander"] details{{border:0}}
      div[data-testid="stExpander"] summary{{font-size:16px; padding:{SPACE_LG}}}
      div[data-testid="stAlert"]{{border-radius:{RADIUS_SM};
        border:1px solid var(--hairline); font-size:14px; line-height:1.4}}
      [data-testid="stCaptionContainer"] p{{font-size:14px!important;
        color:var(--muted)!important; line-height:1.4}}
      hr{{border-color:var(--hairline)}}
      a{{color:var(--blue)}}

      /* Figures are media cards: 22px radius, no shadow. */
      .stMarkdown svg{{border-radius:{RADIUS_LG}; background:{p["figure-surface"]};
        border:1px solid var(--card-border)}}

      /* Phase 34 taxonomy deck. A host-page fragment rather than an iframe (see
         src/dashboard/deck.py), so its type comes from the rules above and only
         the card geometry is new. auto-fit rather than a fixed column count:
         three cards at 1180px, one at phone width, no media query. */
      .deck{{display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr));
        gap:{SPACE_XL}; margin:{SPACE_XL} 0 0 0}}
      .tcard{{background:var(--canvas); border:1px solid var(--hairline);
        border-radius:{RADIUS_MD}; padding:{SPACE_XL}; display:flex;
        flex-direction:column; gap:{SPACE_MD}}}
      /* The four directionally unresolved constructs: dashed border, muted chip
         and the literal words "counted as zero" -- the same three channels
         charts.py uses for an inert bar, because a reader who takes all ten cards
         as equally load-bearing has been misled by the deck. */
      .tcard.is-polar{{border-style:dashed}}
      .tcard .tkey{{font-family:{FONT_MONO}; font-size:12px; letter-spacing:.28px;
        text-transform:uppercase; color:var(--slate)}}
      .tcard .tname{{font-family:{FONT_DISPLAY}; font-size:28px!important;
        line-height:1.15!important; letter-spacing:-.28px!important;
        margin:0!important; color:var(--ink)}}
      .tcard .tplain{{font-size:16px; line-height:1.45; color:var(--body-muted);
        margin:0}}
      .tcard .tchips{{display:flex; flex-wrap:wrap; gap:{SPACE_SM}}}
      .tchip{{display:inline-block; border:1px solid var(--coral); color:var(--coral);
        border-radius:{RADIUS_XL}; padding:3px 10px; font-size:12px; line-height:1.5}}
      .tchip.is-muted{{border-color:var(--hairline); color:var(--slate)}}
      /* Washes come from the mode-aware tokens, never from the fixed pale-blue and
         pale-green constants in :root. Those two do not flip, so a card painted
         with them keeps a near-white fill under dark mode's near-white ink -- the
         classic half-filled-palette failure, visible only in a browser. */
      .tcard .tdef{{font-size:14px; line-height:1.5; color:var(--ink);
        background:var(--stone); border-radius:{RADIUS_SM};
        padding:{SPACE_MD}; margin:0}}
      .tex{{border-left:2px solid var(--hairline); padding-left:{SPACE_MD}}}
      .tex.is-yes{{border-left-color:var(--deep-green)}}
      .tex .texl{{font-family:{FONT_MONO}; font-size:12px; letter-spacing:.28px;
        text-transform:uppercase; color:var(--slate)}}
      .tex ul{{margin:{SPACE_XS} 0 0 0; padding-left:{SPACE_LG}}}
      .tex li{{font-size:14px!important; line-height:1.45; color:var(--ink)}}
      .tex.is-no li{{color:var(--body-muted)}}
      .tcard .tedge{{font-size:12px; line-height:1.45; color:var(--muted); margin:0}}
      .tcard .tfoot{{margin-top:auto; padding-top:{SPACE_MD};
        border-top:1px solid var(--hairline); display:flex; flex-wrap:wrap;
        gap:{SPACE_SM}; align-items:baseline}}
      .tcard .tinst{{font-size:12px; line-height:1.45; color:var(--slate);
        flex:1 1 100%}}
      .tanchor{{font-family:{FONT_MONO}; font-size:12px; background:var(--stone);
        color:var(--ink); border-radius:{RADIUS_XS}; padding:2px 6px}}

      .stTabs [data-baseweb="tab-list"]{{gap:{SPACE_XL};
        border-bottom:1px solid var(--hairline)}}
      .stTabs [data-baseweb="tab"]{{font-size:16px; padding:{SPACE_MD} 0;
        color:var(--body-muted)}}
      .stTabs [aria-selected="true"]{{color:var(--ink)!important}}
      .stTabs [data-baseweb="tab-highlight"]{{background:var(--ink)!important}}
    </style>
    """
    # Every line unindented, not merely dedented: `st.markdown` turns any line
    # with four leading spaces into a code fence, and the rules inside @media
    # blocks are indented further than the block itself.
    return "\n".join(line.strip() for line in css.splitlines() if line.strip())


def lede(text: str) -> str:
    """Wrap a paragraph of copy in the lede style, honouring **bold**.

    The copy in `copy.py` is markdown, and the pages render it inside a styled
    `<p>` where markdown is not parsed -- so `**not**` reached the screen with
    its asterisks showing. Found by reading the page, not by a test: the string
    was correct at every layer, and only the final render was wrong.
    """
    parts = text.split("**")
    rendered = "".join(
        part if index % 2 == 0 else f"<strong>{part}</strong>" for index, part in enumerate(parts)
    )
    return f'<p class="lede">{rendered}</p>'


# ---------------------------------------------------------------------------
# Claude (DESIGNclaude.md) -- Page 2 only
# ---------------------------------------------------------------------------
#
# One page in this app runs a different design language, on purpose: "Score my
# own text" is where a reader hands over their own words, and the brief asked
# for Claude's warm editorial surface there and nowhere else. Keeping it to one
# page is also what `DESIGNclaude.md` itself asks for -- it says not to repeat a
# surface mode across consecutive bands, and a whole app painted cream would
# make the coral CTA meaningless.
#
# Token names below mirror DESIGNclaude.md exactly so the file and the code can
# be read side by side. No token from `DESIGNcohere.md` is used on that page and
# none of these leak back onto the dashboard: `tests/test_dashboard_pages.py`
# asserts the separation in both directions.

CLAUDE_CANVAS = "#faf9f5"
CLAUDE_SURFACE_CARD = "#efe9de"
CLAUDE_SURFACE_SOFT = "#f5f0e8"
CLAUDE_SURFACE_DARK = "#181715"
CLAUDE_SURFACE_DARK_ELEVATED = "#252320"
CLAUDE_SURFACE_DARK_SOFT = "#1f1e1b"
CLAUDE_PRIMARY = "#cc785c"
CLAUDE_PRIMARY_ACTIVE = "#a9583e"
CLAUDE_INK = "#141413"
CLAUDE_BODY = "#3d3d3a"
CLAUDE_MUTED = "#6c6a64"
CLAUDE_MUTED_SOFT = "#8e8b82"
CLAUDE_HAIRLINE = "#e6dfd8"
CLAUDE_ON_DARK = "#faf9f5"
CLAUDE_ON_DARK_SOFT = "#a09d96"

#: Copernicus and StyreneB are licensed and unavailable (DESIGNclaude.md, Known
#: Gaps). The documented substitutes are the implementation: EB Garamond for the
#: serif display, Inter for the humanist sans, JetBrains Mono for code.
CLAUDE_FONT_DISPLAY = '"EB Garamond", "Tiempos Headline", Garamond, "Times New Roman", serif'
CLAUDE_FONT_UI = 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
CLAUDE_FONT_MONO = '"JetBrains Mono", ui-monospace, Menlo, monospace'

#: Light and dark for the Claude surface. Dark is not invented here either:
#: `DESIGNclaude.md` already documents a full dark surface family -- surface-dark
#: #181715 for product mockups and the footer, surface-dark-elevated #252320 for
#: cards inside those bands, on-dark #faf9f5 for text, on-dark-soft #a09d96 for
#: secondary labels. Dark mode promotes that family to the page floor.
#:
#: The coral does not change. The system's CTA is coral on cream and coral on
#: dark; it is the brand voltage, not a light-mode accent.
CLAUDE_LIGHT: dict[str, str] = {
    "canvas": CLAUDE_CANVAS,
    "card": CLAUDE_SURFACE_CARD,
    "soft": CLAUDE_SURFACE_SOFT,
    "dark": CLAUDE_SURFACE_DARK,
    "ink": CLAUDE_INK,
    "body": CLAUDE_BODY,
    "muted": CLAUDE_MUTED,
    "muted-soft": CLAUDE_MUTED_SOFT,
    "hairline": CLAUDE_HAIRLINE,
    "primary": CLAUDE_PRIMARY,
    "on-primary": "#ffffff",
    "figure-surface": "#ffffff",
}

CLAUDE_DARK: dict[str, str] = {
    "canvas": CLAUDE_SURFACE_DARK,
    "card": CLAUDE_SURFACE_DARK_ELEVATED,
    "soft": CLAUDE_SURFACE_DARK_SOFT,
    "dark": CLAUDE_SURFACE_DARK_SOFT,
    "ink": CLAUDE_ON_DARK,
    "body": "#cdc9c1",  # a step up from on-dark-soft, which is a label tone
    "muted": CLAUDE_ON_DARK_SOFT,
    "muted-soft": CLAUDE_ON_DARK_SOFT,
    "hairline": "#332f2a",
    "primary": CLAUDE_PRIMARY,
    "on-primary": "#ffffff",
    "figure-surface": "#ffffff",
}

CLAUDE_MODES: dict[str, dict[str, str]] = {"light": CLAUDE_LIGHT, "dark": CLAUDE_DARK}


def claude_palette(mode: str) -> dict[str, str]:
    """The Claude token set for a mode, falling back rather than half-painting."""
    return CLAUDE_MODES.get(mode, CLAUDE_MODES[DEFAULT_MODE])


CLAUDE_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    "family=EB+Garamond:wght@400;500&family=Inter:wght@400;500&"
    'family=JetBrains+Mono:wght@400&display=swap">'
)


def claude_css(mode: str = DEFAULT_MODE) -> str:
    """Page 2's stylesheet for one mode. Serif display, coral CTA, both surfaces.

    Page 2 follows the dashboard's light/dark choice, in its own language: the
    cream canvas becomes `surface-dark`, the cream feature cards become
    `surface-dark-elevated`, and the text roles invert to `on-dark`. The coral
    is the one thing that does not move.
    """
    c = claude_palette(mode)
    css = f"""
    {CLAUDE_FONTS}
    <style>
      :root{{
        --c-canvas:{c["canvas"]}; --c-card:{c["card"]};
        --c-soft:{c["soft"]}; --c-dark:{c["dark"]};
        --c-dark-soft:{CLAUDE_SURFACE_DARK_SOFT}; --c-primary:{c["primary"]};
        --c-ink:{c["ink"]}; --c-body:{c["body"]}; --c-muted:{c["muted"]};
        --c-muted-soft:{c["muted-soft"]}; --c-hairline:{c["hairline"]};
        --c-on-dark:{c["ink"]};
      }}
      html, body, .stApp, [class*="css"]{{
        font-family:{CLAUDE_FONT_UI}; color:var(--c-ink); background:var(--c-canvas);
      }}
      .block-container{{padding-top:48px; padding-bottom:96px; max-width:1200px}}
      /* Same reason as the dashboard: Streamlit's header and sidebar come from
         the static theme config and cannot follow a runtime mode. */
      [data-testid="stHeader"]{{background:transparent}}
      [data-testid="stSidebar"]{{background:var(--c-soft);
        border-right:1px solid var(--c-hairline)}}
      [data-testid="stSidebar"] *{{color:var(--c-ink)}}

      /* Display tier is serif at weight 400 with negative tracking -- the brand
         voice. Bolding it, or swapping in the sans, is the one thing
         DESIGNclaude.md calls unbreakable. */
      h1{{font-family:{CLAUDE_FONT_DISPLAY}!important; font-size:64px!important;
        font-weight:400!important; line-height:1.05!important;
        letter-spacing:-1.5px!important; color:var(--c-ink); margin:0 0 24px 0!important}}
      h2{{font-family:{CLAUDE_FONT_DISPLAY}!important; font-size:36px!important;
        font-weight:400!important; line-height:1.15!important;
        letter-spacing:-.5px!important; margin-top:96px!important;
        margin-bottom:16px!important; color:var(--c-ink)}}
      h3{{font-family:{CLAUDE_FONT_DISPLAY}!important; font-size:28px!important;
        font-weight:400!important; letter-spacing:-.3px!important}}
      p, li{{font-size:16px; line-height:1.55; color:var(--c-body)}}
      .lede{{font-size:18px; line-height:1.55; max-width:68ch; color:var(--c-body);
        margin-bottom:24px}}
      .mono-label{{font-family:{CLAUDE_FONT_UI}; font-size:12px; font-weight:500;
        letter-spacing:1.5px; text-transform:uppercase; color:var(--c-muted)}}


      /* The score is a full-bleed coral callout -- the system's voltage moment,
         used once on the page and nowhere else. */
      .hero-figure{{background:var(--c-primary); color:{c["on-primary"]};
        border-radius:12px;
        padding:48px}}
      .hero-figure .hv{{font-family:{CLAUDE_FONT_DISPLAY}; font-size:64px;
        font-weight:400; line-height:1.05; letter-spacing:-1.5px; display:block;
        margin:8px 0}}
      .hero-figure .hl{{font-size:12px; font-weight:500; letter-spacing:1.5px;
        text-transform:uppercase; opacity:.85}}

      /* Band chip: badge-pill geometry on the cream card surface. */
      .band{{display:inline-block; background:var(--c-card); color:var(--c-ink);
        border:0; border-radius:9999px; padding:4px 12px; font-size:13px;
        font-weight:500; line-height:1.4}}

      /* Dimension tiles are feature-cards: one step darker than canvas. */
      .widget{{background:var(--c-card); border-radius:12px; padding:24px;
        min-height:180px; height:100%; display:flex; flex-direction:column;
        justify-content:space-between}}
      .widget.is-inert{{background:transparent; border:1px solid var(--c-hairline)}}
      .widget .wl{{font-size:12px; font-weight:500; letter-spacing:1.5px;
        text-transform:uppercase; color:var(--c-muted); display:block;
        margin-bottom:12px; min-height:32px}}
      .widget .wv{{font-family:{CLAUDE_FONT_DISPLAY}; font-size:36px; font-weight:400;
        line-height:1.15; letter-spacing:-.5px; color:var(--c-ink); display:block}}
      .widget .wu{{font-size:14px; line-height:1.55; color:var(--c-muted);
        display:block; margin-top:8px}}
      [data-testid="stHorizontalBlock"]{{gap:24px}}
      [data-testid="stColumn"] > div{{height:100%}}

      /* Coral CTA at 40px, 8px radius; darkens on press and does nothing else. */
      .stButton > button{{background:var(--c-primary); border:0; border-radius:8px;
        padding:12px 20px; height:40px; font-size:14px; font-weight:500}}
      .stButton > button p, .stButton > button div, .stButton > button span{{
        color:#ffffff!important; font-size:14px; font-weight:500}}
      .stButton > button:active{{background:{CLAUDE_PRIMARY_ACTIVE}}}

      /* Inputs: cream fill, hairline border, coral focus ring. */
      .stTextArea textarea, .stTextInput input{{background:var(--c-canvas);
        color:var(--c-ink); border:1px solid var(--c-hairline)!important;
        border-radius:8px!important; font-size:16px!important; padding:10px 14px!important}}
      .stTextArea textarea:focus, .stTextInput input:focus{{
        border-color:var(--c-primary)!important;
        box-shadow:0 0 0 3px rgba(204,120,92,.15)!important}}
      div[data-baseweb="select"] > div{{background:var(--c-canvas)!important;
        border:1px solid var(--c-hairline)!important; border-radius:8px!important;
        color:var(--c-ink)!important; font-size:16px!important}}
      label p{{font-size:14px!important; color:var(--c-muted)!important}}

      blockquote{{border-left:2px solid var(--c-primary)!important;
        background:var(--c-soft); border-radius:0 12px 12px 0;
        padding:16px 24px!important; margin:24px 0!important}}
      blockquote p{{font-size:18px!important; line-height:1.55; color:var(--c-ink)!important}}
      code, kbd{{font-family:{CLAUDE_FONT_MONO}!important; font-size:14px!important;
        background:var(--c-card)!important; border-radius:4px}}
      div[data-testid="stExpander"]{{border:1px solid var(--c-hairline);
        border-radius:12px; background:var(--c-canvas)}}
      div[data-testid="stExpander"] details{{border:0}}
      div[data-testid="stExpander"] summary{{font-size:16px; padding:24px}}
      div[data-testid="stAlert"]{{border-radius:12px;
        border:1px solid var(--c-hairline); font-size:14px; line-height:1.55}}
      [data-testid="stCaptionContainer"] p{{font-size:13px!important;
        color:var(--c-muted-soft)!important; line-height:1.4}}
      a{{color:var(--c-primary)}}
      hr{{border-color:var(--c-hairline)}}
      .stMarkdown svg{{border-radius:12px; background:{c["figure-surface"]};
        border:1px solid var(--c-hairline)}}
      [data-testid="stSelectbox"] div{{background-color:var(--c-canvas)!important}}
      [data-testid="stSelectbox"] *{{color:var(--c-ink)!important}}
      [data-testid="stSelectbox"] svg{{fill:var(--c-ink)!important}}
      /* Same defect as the dashboard's, in this language: the dropped list is
         portalled out of the widget, so on the dark surface a white sheet of
         options opened over the page. See the matching block in `app_css`. */
      [data-testid="stSelectboxVirtualDropdown"]{{background:var(--c-canvas)!important;
        border:1px solid var(--c-hairline)!important}}
      [data-testid="stSelectboxVirtualDropdown"] *{{color:var(--c-ink)!important}}
      [data-testid="stSelectboxVirtualDropdown"] [role="option"]{{
        background:var(--c-canvas)!important}}
      [data-testid="stSelectboxVirtualDropdown"] [role="option"]:hover,
      [data-testid="stSelectboxVirtualDropdown"] [aria-selected="true"]{{
        background:var(--c-card)!important}}
      [data-testid="stStatusWidget"], [data-testid="stStatusWidget"] *{{
        color:var(--c-ink)!important; fill:var(--c-ink)!important}}
      [data-baseweb="tooltip"], [data-baseweb="tooltip"] *{{
        background:var(--c-card)!important; color:var(--c-ink)!important}}
      .stTextArea textarea{{background:var(--c-canvas)!important}}
      [data-testid="stSidebarNav"] a[href*="Signal_detail"]{{display:none}}
      {_cognitive_nav_css()}
    </style>
    """
    return "\n".join(line.strip() for line in css.splitlines() if line.strip())


def claude_lede(text: str) -> str:
    parts = text.split("**")
    rendered = "".join(
        part if index % 2 == 0 else f"<strong>{part}</strong>" for index, part in enumerate(parts)
    )
    return f'<p class="lede">{rendered}</p>'
