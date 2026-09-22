"""Loads, validates and freezes `config/instruments.yaml`.

Why a loader and not a dict in a module
---------------------------------------
Same argument `atlas_map.py` makes, and this module is deliberately its twin:
the mapping is evidence-shaped -- it says a construct belongs to a published
psychometric instrument -- so it belongs in a reviewable file with its citation
beside each row, not scattered through a renderer. The conventions here
(`lru_cache`, the recursive numeric walk, the bib-key regex) are copied from
that module rather than reinvented, because two loaders that disagree about
what a citation is are two rules.

The copyright rule, which is the one that matters
--------------------------------------------------
CSAI-2, the ABQ, CD-RISC and TAIS are copyrighted. This project maps to them; it
does not implement them. `SubscaleRow.prompt` -- the "topic the reader could ask
about" that Phase 32 renders for an unevidenced subscale -- is derived at load
time from the `definition` field in `config/taxonomy.yaml`, which this project
authored, and there is no code path by which `instruments.yaml` can supply it.
That is enforced by construction: `prompt` is not read from the instruments file
at all, and `load_instruments` refuses any row carrying a field it does not
recognise, so a `prompt:` key added to the YAML next month is a failure rather
than a quiet override.

What this module refuses, and why each refusal is a refusal rather than a warning
--------------------------------------------------------------------------------
* **A subscale that is not a taxonomy construct.** A row on screen for a
  construct the model does not predict would be scored off some other row.
* **A taxonomy construct with no row.** The reverse gap is worse: the table
  would show nine of ten and nobody counts rows. `atlas_map.py` records exactly
  this argument.
* **A construct named by two instruments.** The denominator is "instruments this
  text speaks to"; double-counting a construct makes that denominator a fiction
  while the table still looks right.
* **A citation that does not resolve in `paper/refs.bib`.** The anchor supports
  the *construct*, which is the only claim this file is entitled to make.
* **Any numeric field, anywhere.** A number here would reach the screen with no
  provenance. Coverage state comes from `DashboardView.bars` at render time.
* **Any unrecognised field.** See the copyright rule above.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTRUMENTS_PATH = REPO_ROOT / "config" / "instruments.yaml"
TAXONOMY_PATH = REPO_ROOT / "config" / "taxonomy.yaml"
REFS_PATH = REPO_ROOT / "paper" / "refs.bib"

#: The only keys an instrument row may carry. A closed set rather than an open
#: one, because the field this file must never grow is a question -- see the
#: copyright note in the module docstring.
ROW_FIELDS = frozenset({"instrument", "full_name", "citation", "subscales"})

#: File metadata, never rendered, exempt from the numeric walk. The same names
#: `atlas_map._reject_numbers` exempts, kept identical so the two config files
#: can be read against each other.
METADATA_KEYS = frozenset({"version", "phase"})


class InstrumentError(ValueError):
    """Raised when `instruments.yaml` says something it is not entitled to say."""


@dataclass(frozen=True)
class SubscaleRow:
    """One construct, as a subscale of the instrument it was taken from.

    `prompt` is the topic a reader could raise when this subscale went
    unevidenced. It is derived from the taxonomy's own `definition` and is
    **not** an instrument item; see the module docstring.
    """

    construct: str
    prompt: str

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise InstrumentError(
                f"{self.construct!r} has no prompt. The prompt is derived from the "
                "taxonomy's own definition; an empty one means that taxonomy entry "
                "lost its definition, not that a prompt should be written here."
            )


@dataclass(frozen=True)
class InstrumentRow:
    """One published instrument and the subscales this project carries for it."""

    key: str
    instrument: str
    full_name: str
    citation: str
    subscales: tuple[SubscaleRow, ...]

    def __post_init__(self) -> None:
        if not self.instrument.strip():
            raise InstrumentError(f"{self.key!r} has no instrument name.")
        if not self.citation.strip():
            raise InstrumentError(
                f"{self.key!r} has no citation. Every row names the reference that "
                "supports the construct; an uncited row is a mapping that reads as "
                "grounded and is not."
            )
        if not self.subscales:
            raise InstrumentError(f"{self.key!r} covers no subscale.")

    @property
    def constructs(self) -> tuple[str, ...]:
        return tuple(s.construct for s in self.subscales)


@dataclass(frozen=True)
class InstrumentSet:
    """The whole validated file, frozen."""

    rows: tuple[InstrumentRow, ...]

    def row_for(self, construct: str) -> InstrumentRow:
        for row in self.rows:
            if construct in row.constructs:
                return row
        raise KeyError(f"{construct!r} has no instrument row in instruments.yaml")

    @property
    def constructs(self) -> tuple[str, ...]:
        return tuple(c for row in self.rows for c in row.constructs)


def _reject_numbers(node: object, path: str = "") -> None:
    """Walk the parsed YAML and refuse any number anywhere in it.

    Recursive rather than a check on known keys, for the reason
    `atlas_map._reject_numbers` gives: a field nobody thought of is exactly the
    field that gets through a key-by-key check.
    """
    if isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        if path in METADATA_KEYS:
            return
        raise InstrumentError(
            f"instruments.yaml carries a number at {path!r} ({node!r}). This file "
            "holds no values: coverage state is read off DashboardView.bars at "
            "render time, and a constant written here would reach the screen with "
            "no provenance."
        )
    if isinstance(node, dict):
        for key, value in node.items():
            _reject_numbers(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _reject_numbers(value, f"{path}[{index}]")


@lru_cache(maxsize=1)
def _taxonomy() -> dict:
    data = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))
    return data["constructs"]


@lru_cache(maxsize=1)
def _bib_keys() -> frozenset[str]:
    """Every citation key in `paper/refs.bib`. Read, never hardcoded."""
    if not REFS_PATH.exists():
        raise InstrumentError(f"{REFS_PATH} is missing; instrument citations cannot be checked.")
    return frozenset(re.findall(r"^@\w+\{([^,]+),", REFS_PATH.read_text(encoding="utf-8"), re.M))


def _cited_keys(citation: str) -> tuple[str, ...]:
    """The keys inside a `[Key1; Key2]` citation, in the taxonomy's own form."""
    inner = citation.strip().lstrip("[").rstrip("]")
    return tuple(part.strip() for part in inner.split(";") if part.strip())


def prompt_for(construct: str) -> str:
    """The topic a reader could raise, taken from the taxonomy's own definition.

    The first sentence of `definition`, normalised. Deliberately a derivation
    rather than an authored string: an authored one would drift towards sounding
    like the instrument it names, which is the failure this module is shaped to
    prevent.
    """
    entry = _taxonomy().get(construct)
    if entry is None:
        raise InstrumentError(f"{construct!r} is not in the frozen taxonomy.")
    definition = " ".join(str(entry.get("definition", "")).split())
    return definition.split(". ")[0].rstrip(".")


@lru_cache(maxsize=1)
def load_instruments(path: str | None = None) -> InstrumentSet:
    """Load, validate and freeze the instrument set. Cached: the file is static."""
    source = Path(path) if path else INSTRUMENTS_PATH
    if not source.exists():
        raise InstrumentError(f"{source} is missing; the coverage panel cannot render.")
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    _reject_numbers(data)

    rows: list[InstrumentRow] = []
    for key, entry in (data.get("instruments") or {}).items():
        if unknown := set(entry) - ROW_FIELDS:
            raise InstrumentError(
                f"{key!r} carries unrecognised field(s) {sorted(unknown)}. The field "
                "set is closed on purpose: the one field this file must never grow "
                "is a question, because the instruments it names are copyrighted."
            )
        rows.append(
            InstrumentRow(
                key=key,
                instrument=str(entry.get("instrument", "")),
                full_name=str(entry.get("full_name", "")),
                citation=str(entry.get("citation", "")),
                subscales=tuple(
                    SubscaleRow(construct=c, prompt=prompt_for(c))
                    for c in (entry.get("subscales") or ())
                ),
            )
        )

    taxonomy = frozenset(_taxonomy())
    named: list[str] = [c for row in rows for c in row.constructs]
    if extra := set(named) - taxonomy:
        raise InstrumentError(
            f"instruments.yaml names {sorted(extra)}, which are not in the frozen "
            "taxonomy. A row for a construct the model does not predict would be "
            "scored off some other construct's state."
        )
    if missing := taxonomy - set(named):
        raise InstrumentError(
            f"instruments.yaml has no row for {sorted(missing)}. Every construct "
            "belongs to exactly one instrument; a construct with no row disappears "
            "from the table and nobody counts rows."
        )
    if duplicated := {c for c in named if named.count(c) > 1}:
        raise InstrumentError(
            f"instruments.yaml counts {sorted(duplicated)} under two instruments. "
            "The denominator is 'instruments this text speaks to'; double-counting "
            "a construct makes it a fiction while the table still looks right."
        )

    keys = _bib_keys()
    for row in rows:
        cited = _cited_keys(row.citation)
        if not cited:
            raise InstrumentError(f"{row.key!r} has a citation with no keys in it.")
        for citation_key in cited:
            if citation_key not in keys:
                raise InstrumentError(
                    f"{row.key!r} cites {citation_key!r}, which does not resolve in "
                    f"{REFS_PATH.name}."
                )

    return InstrumentSet(rows=tuple(rows))
