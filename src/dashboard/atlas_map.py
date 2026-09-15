"""Loads, validates and freezes `config/brain_atlas.yaml`.

Why a loader and not a dict in a module
---------------------------------------
The mapping is evidence-shaped: it says a construct is associated with a brain
region, which is the strongest-sounding claim anything in this repository makes
and the only one with no data behind it at all. A claim like that belongs in a
reviewable file with the reasoning beside each row, not scattered through a
renderer. `config/taxonomy.yaml` made the same argument for the constructs
themselves and the `instrument_anchor` convention here is copied from it.

What this module refuses, and why each refusal is a refusal rather than a warning
--------------------------------------------------------------------------------
* **A construct in the atlas that is not in the taxonomy.** The taxonomy is
  frozen at Phase 12; a name that drifts here would put a node on screen for a
  construct the model does not predict, and the node would be lit by a
  probability read off some other row.
* **A construct in the taxonomy with no row here.** The reverse gap is worse:
  the figure would silently show nine of ten and nobody counts nodes.
* **A mapped row with no `instrument_anchor` that resolves in `paper/refs.bib`.**
  The anchor supports the *construct*, not the region -- see the file's header.
* **A mapped row with no `network_evidence`.** This is the field that says what
  supports the *region*, and today every value is an admission that nothing in
  this repository does. A row without it would be a mapping that looks cited.
* **Any numeric field, anywhere in the file.** A number here would be a constant
  that reaches the screen with no provenance -- precisely what `ScoreSurface`
  exists to prevent, arriving through a config file instead of through code.
  Node size and colour come from `DashboardView.bars` at render time or they do
  not come at all.

Geometry is deliberately NOT in the YAML. Where a node sits is presentation, it
changes when the figure is redesigned, and a coordinate living beside a citation
invites the next reader to think the coordinate is cited too. It lives in
`neurovis.py` with the rest of the drawing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ATLAS_PATH = REPO_ROOT / "config" / "brain_atlas.yaml"
TAXONOMY_PATH = REPO_ROOT / "config" / "taxonomy.yaml"
REFS_PATH = REPO_ROOT / "paper" / "refs.bib"

#: The only values `network_evidence` may take. Both of them say that nothing in
#: this repository supports the region; they differ in *why*. A future value
#: naming a real source has to be added here deliberately, beside a test, rather
#: than appearing in the YAML and being accepted because the field was non-empty.
EVIDENCE_STATES: dict[str, str] = {
    "none_in_repository": "no imaging source here — hypothesised association, not imaging",
    "outside_athlete_population": (
        "imaging is from workplace burnout, not athletes — hypothesised association, not imaging"
    ),
}

#: The same states in a form that fits a table cell.
#:
#: Two forms rather than one because rendering the full sentence in every row
#: made the table ten lines deep per construct and pushed the figure off the
#: screen -- found by screenshotting the panel, which is the only place that
#: failure is visible. The short form is a pointer, never a softening: the full
#: sentence appears once under the table, and the words the Phase 26 gate turns
#: on are in the panel's stamp and caption regardless of what a cell says.
EVIDENCE_SHORT: dict[str, str] = {
    "none_in_repository": "no imaging source here",
    "outside_athlete_population": "different population — see note",
}


class AtlasError(ValueError):
    """Raised when `brain_atlas.yaml` says something it is not entitled to say."""


@dataclass(frozen=True)
class Region:
    """One anatomical label, in both registers."""

    key: str
    anatomical: str
    plain_name: str


@dataclass(frozen=True)
class AtlasRow:
    """One construct's row: where it is drawn, and what does and does not back it.

    `unmapped` rows carry no region and no network, and their `evidence_note` is
    the reason they were left out. They are rendered, visibly, as unmapped --
    dropping them would turn a deliberate gap into an invisible one.
    """

    construct: str
    unmapped: bool
    regions: tuple[str, ...]
    networks: tuple[str, ...]
    instrument_anchor: str
    network_evidence: str
    rationale: str

    def __post_init__(self) -> None:
        if not self.instrument_anchor.strip():
            raise AtlasError(
                f"{self.construct!r} has no instrument_anchor. Every row names the "
                "reference that supports the construct, even an unmapped one."
            )
        if self.unmapped:
            if self.regions or self.networks:
                raise AtlasError(f"{self.construct!r} is unmapped but names a region.")
            if not self.rationale.strip():
                raise AtlasError(f"unmapped {self.construct!r} gives no reason.")
            return
        if not self.regions:
            raise AtlasError(f"{self.construct!r} is mapped to no region.")
        if not self.networks:
            raise AtlasError(f"{self.construct!r} is mapped to no network.")
        if self.network_evidence not in EVIDENCE_STATES:
            raise AtlasError(
                f"{self.construct!r} has network_evidence={self.network_evidence!r}, "
                f"which is not one of {sorted(EVIDENCE_STATES)}. This field is what "
                "states that nothing in this repository supports the region; a row "
                "without it is a mapping that reads as cited."
            )
        if not self.rationale.strip():
            raise AtlasError(f"{self.construct!r} is mapped with no rationale.")

    @property
    def primary_region(self) -> str:
        """Where the node is drawn. The rest are listed in the node's label."""
        return self.regions[0]

    @property
    def evidence_note(self) -> str:
        """The full sentence. Printed under the table, never as a tooltip."""
        if self.unmapped:
            return "unmapped — " + " ".join(self.rationale.split())
        return EVIDENCE_STATES[self.network_evidence]

    @property
    def evidence_short(self) -> str:
        """The table-cell form. See `EVIDENCE_SHORT` for why there are two."""
        if self.unmapped:
            return "unmapped — see below"
        return EVIDENCE_SHORT[self.network_evidence]


@dataclass(frozen=True)
class BrainAtlas:
    """The whole validated file, frozen."""

    rows: tuple[AtlasRow, ...]
    regions: dict[str, Region]
    network_names: dict[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "regions", MappingProxyType(dict(self.regions)))
        object.__setattr__(self, "network_names", MappingProxyType(dict(self.network_names)))

    def row(self, construct: str) -> AtlasRow:
        for row in self.rows:
            if row.construct == construct:
                return row
        raise KeyError(f"{construct!r} has no row in brain_atlas.yaml")

    @property
    def mapped(self) -> tuple[AtlasRow, ...]:
        return tuple(r for r in self.rows if not r.unmapped)

    @property
    def unmapped(self) -> tuple[AtlasRow, ...]:
        return tuple(r for r in self.rows if r.unmapped)

    def edges(self) -> tuple[tuple[str, str, str], ...]:
        """(construct_a, construct_b, shared_network), derived not drawn.

        Two constructs are linked when the file gives them a network in common.
        Deriving the edges means a mapping change moves the picture; a hand-drawn
        edge list would survive the change and quietly assert a link the file no
        longer makes.
        """
        out: list[tuple[str, str, str]] = []
        mapped = self.mapped
        for i, a in enumerate(mapped):
            for b in mapped[i + 1 :]:
                shared = sorted(set(a.networks) & set(b.networks))
                if shared:
                    out.append((a.construct, b.construct, shared[0]))
        return tuple(out)


def _reject_numbers(node: object, path: str = "") -> None:
    """Walk the parsed YAML and refuse any number anywhere in it.

    Recursive rather than a check on known keys, because the failure this
    prevents is somebody adding a `weight:` or an `intensity:` that nothing
    validates -- a field nobody thought of is exactly the field that gets
    through a key-by-key check.
    """
    if isinstance(node, bool):  # bool is an int subclass; `unmapped: true` is fine
        return
    if isinstance(node, (int, float)):
        if path in ("version", "phase"):  # file metadata, never rendered
            return
        raise AtlasError(
            f"brain_atlas.yaml carries a number at {path!r} ({node!r}). This file "
            "holds no values: a constant written here would reach the screen with "
            "no provenance, which is what ScoreSurface exists to prevent."
        )
    if isinstance(node, dict):
        for key, value in node.items():
            _reject_numbers(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _reject_numbers(value, f"{path}[{index}]")


@lru_cache(maxsize=1)
def _taxonomy_constructs() -> frozenset[str]:
    data = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))
    return frozenset(data["constructs"])


@lru_cache(maxsize=1)
def _bib_keys() -> frozenset[str]:
    """Every citation key in `paper/refs.bib`.

    Read rather than imported, because the alternative is a hardcoded list that
    is correct on the day it is written. The owner's standing instruction is
    that nothing is added to that file, so this loader's job is to prove every
    anchor already resolves there -- not to grow it.
    """
    if not REFS_PATH.exists():
        raise AtlasError(f"{REFS_PATH} is missing; atlas anchors cannot be checked.")
    return frozenset(re.findall(r"^@\w+\{([^,]+),", REFS_PATH.read_text(encoding="utf-8"), re.M))


@lru_cache(maxsize=1)
def load_atlas(path: str | None = None) -> BrainAtlas:
    """Load, validate and freeze the atlas. Cached: the file does not change."""
    source = Path(path) if path else ATLAS_PATH
    if not source.exists():
        raise AtlasError(f"{source} is missing; the brain atlas page cannot render.")
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    _reject_numbers(data)

    regions = {
        key: Region(key=key, anatomical=value["anatomical"], plain_name=value["plain_name"])
        for key, value in (data.get("regions") or {}).items()
    }
    network_names = {
        key: value["plain_name"] for key, value in (data.get("networks") or {}).items()
    }

    rows: list[AtlasRow] = []
    for construct, entry in (data.get("constructs") or {}).items():
        row = AtlasRow(
            construct=construct,
            unmapped=bool(entry.get("unmapped", False)),
            regions=tuple(entry.get("regions") or ()),
            networks=tuple(entry.get("networks") or ()),
            instrument_anchor=str(entry.get("instrument_anchor", "")),
            network_evidence=str(entry.get("network_evidence", "")),
            rationale=str(entry.get("rationale") or entry.get("unmapped_reason") or ""),
        )
        for region in row.regions:
            if region not in regions:
                raise AtlasError(f"{construct!r} names region {region!r}, which is undefined.")
        for network in row.networks:
            if network not in network_names:
                raise AtlasError(f"{construct!r} names network {network!r}, which is undefined.")
        rows.append(row)

    taxonomy = _taxonomy_constructs()
    named = {row.construct for row in rows}
    if extra := named - taxonomy:
        raise AtlasError(
            f"brain_atlas.yaml maps {sorted(extra)}, which are not in the frozen taxonomy. "
            "A node for a construct the model does not predict would be lit by some "
            "other construct's probability."
        )
    if missing := taxonomy - named:
        raise AtlasError(
            f"brain_atlas.yaml has no row for {sorted(missing)}. Every construct is "
            "mapped or explicitly unmapped; a construct with no row disappears from the "
            "figure and nobody counts nodes."
        )

    keys = _bib_keys()
    for row in rows:
        if row.instrument_anchor not in keys:
            raise AtlasError(
                f"{row.construct!r} anchors to {row.instrument_anchor!r}, which does not "
                f"resolve in {REFS_PATH.name}."
            )

    return BrainAtlas(
        rows=tuple(sorted(rows, key=lambda r: r.construct)),
        regions=regions,
        network_names=network_names,
    )
