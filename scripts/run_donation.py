#!/usr/bin/env python
"""Category A3 ingestion -- consented donated pre-competition reflections.

    python scripts/run_donation.py --template            # write a blank inbox file
    python scripts/run_donation.py --add donations_inbox.jsonl --source-id a3_donations_v1
    python scripts/run_donation.py --verify-only --source-id a3_donations_v1

READ FIRST: `docs/consent_form.md` and `docs/ethics.md` §4, §7. Every record this
writes is a real person's words, donated under written consent, with a
withdrawal right that has to actually work.

Why A3 and not A5
-----------------
A1 was surveyed at Phase 7 -- four candidates, all post-match, all rejected. A5
topic-scoped forum collection was attempted 2026-08-12 and returned `403
Blocked` on every request; the block was treated as an answer rather than an
obstacle (`docs/ethics.md` §3.5.5). A3 is what remains without registering an
API application, and it was the ethically cleanest route from the start.

The consent gate
----------------
Every donation must carry `consent_confirmed: true`, `consent_form_version`, and
`donor_is_adult: true`. A record missing any of them is **refused and logged**,
not defaulted. There is no `--assume-consent`, and there will not be one: the
whole basis on which this category is permitted is that consent was actually
given, so a flag that lets a caller skip the check would remove the only thing
separating A3 from scraping.

What this script never stores
-----------------------------
**No donor name, email, or contact detail reaches `data/`.** The inbox file may
contain them -- it is how you know whose donation to delete on withdrawal -- but
`_to_record` reads only the text and the coarse metadata. The name↔record_id
mapping is the researcher's responsibility to keep **outside the repository**
(OPEN-032). A signed consent form committed once is committed forever.

Health content
--------------
`docs/consent_form.md` §5 tells donors not to write about injury, illness or
treatment, and P6 prohibits it regardless of what a donor consented to. Donations
matching the health cues are refused here, and the researcher should tell the
donor why rather than silently dropping them.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingestion.allowlist import IngestionRefused, SourceDescriptor, log_refusal  # noqa: E402
from src.ingestion.records import COMPETITION_LEVELS, RawRecord  # noqa: E402
from src.ingestion.reddit import is_health_content, mentions_minor  # noqa: E402
from src.ingestion.store import RawStore  # noqa: E402

CONSENT_FORM_VERSION = "1.0"

TEMPLATE = {
    "donation_id": "d001",
    "consent_confirmed": True,
    "consent_form_version": CONSENT_FORM_VERSION,
    "donor_is_adult": True,
    "consent_date": "2026-08-13",
    "text": "Write the donated reflection here, verbatim, as the donor wrote it.",
    "sport": "running",
    "competition_level": "club",
    "time_to_competition_days": 3,
    "_note": (
        "Donor name/contact may be kept in this inbox file for withdrawal handling. "
        "This file must live OUTSIDE the repository. Nothing here except text, sport, "
        "competition_level and time_to_competition_days reaches data/."
    ),
}


def a3_descriptor(source_id: str, *, collection_date: str | None = None) -> SourceDescriptor:
    return SourceDescriptor(
        source_id=source_id,
        source_name="Consented donated pre-competition reflections",
        allowlist_category="A3_consented_donation",
        url_or_citation="Direct donation; see docs/consent_form.md v" + CONSENT_FORM_VERSION,
        licence_or_consent_basis=(
            f"Written informed consent, docs/consent_form.md version {CONSENT_FORM_VERSION}, "
            "naming this project and the construct-labelling purpose. Withdrawal right "
            "explained and honoured per docs/ethics.md §7, including the stated limit that "
            "models already trained are not retrained retroactively. Donors confirmed 18+."
        ),
        permitted_uses=(
            "De-identification, construct annotation, model training and evaluation within "
            "this project. Aggregate reporting only. No verbatim publication. No "
            "individual-level output."
        ),
        redistribution_permitted=False,
        synthetic=False,
        subject_is_adult=True,
        language="en",
        source_type="journal",
        collection_date=collection_date,
        notes=(
            "A3. Donor identities are NOT stored in data/; the name<->record_id mapping is "
            "kept outside the repository and exists only to action withdrawals (OPEN-032). "
            "deidentified=False until scripts/run_preprocessing.py runs."
        ),
        declares={
            "not_scraped_personal_social_media": True,
            "no_minors": True,
            "not_private_communication": True,
            "licence_and_tos_permit_this_use": True,
            "not_behind_auth_or_paywall": True,
            "not_health_injury_or_treatment_content": True,
            "provenance_is_complete": True,
        },
    )


def _to_record(entry: dict[str, Any], source_id: str, index: int) -> RawRecord:
    """Build a record from a donation. Reads text and coarse metadata only.

    Note what is *not* read: name, email, handle, or anything else identifying.
    Those may exist in the inbox file and must not travel into `data/`.
    """
    level = entry.get("competition_level")
    if level is not None and level not in COMPETITION_LEVELS:
        level = None  # refuse to invent; the donor's answer was out of vocabulary
    return RawRecord(
        record_id=f"{source_id}_{entry.get('donation_id') or f'd{index:03d}'}",
        source_id=source_id,
        text=str(entry["text"]).strip(),
        time_to_competition_days=entry.get("time_to_competition_days"),
        sport=entry.get("sport"),
        competition_level=level,
        source_type="journal",
        language="en",
        synthetic=False,
        deidentified=False,  # Phase 8 flips this, never here
    )


def _check(entry: dict[str, Any], source_id: str, index: int) -> str | None:
    """Return a refusal reason, or None if the donation may be ingested."""
    if not entry.get("consent_confirmed"):
        return "A3_NO_CONSENT: consent_confirmed is not true"
    if entry.get("consent_form_version") != CONSENT_FORM_VERSION:
        return (
            f"A3_CONSENT_VERSION: form version "
            f"{entry.get('consent_form_version')!r} != {CONSENT_FORM_VERSION!r}"
        )
    if not entry.get("donor_is_adult"):
        return "A3_NOT_ADULT: donor_is_adult is not true (P2)"
    text = str(entry.get("text", "")).strip()
    if len(text.split()) < 25:
        return f"A3_TOO_SHORT: {len(text.split())} words < 25"
    health = is_health_content(text)
    if health:
        return f"A3_HEALTH_CONTENT: matched {health!r} (P6) -- tell the donor why"
    minor = mentions_minor(text)
    if minor:
        return f"A3_POSSIBLE_MINOR: matched {minor!r} (P2)"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 7/A3 donation ingestion")
    parser.add_argument("--add", type=Path, default=None, help="JSONL inbox of donations")
    parser.add_argument("--source-id", default="a3_donations_v1")
    parser.add_argument("--raw-root", type=Path, default=None)
    parser.add_argument("--template", action="store_true", help="write a blank inbox file")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)

    if args.template:
        target = Path("donations_inbox.jsonl")
        if target.exists():
            print(f"ERROR: {target} already exists; not overwriting", file=sys.stderr)
            return 2
        target.write_text(json.dumps(TEMPLATE) + "\n", encoding="utf-8")
        print(f"Wrote {target}")
        print("\n  KEEP THIS FILE OUT OF THE REPOSITORY once it holds real donations.")
        print("  It may contain donor names for withdrawal handling; data/ never does.")
        print("  Add it to .gitignore before you put anything real in it.")
        return 0

    store = RawStore(root=args.raw_root) if args.raw_root else RawStore()

    if args.verify_only:
        try:
            provenance, records = store.read_source(args.source_id)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: cannot read {args.source_id!r}: {exc}", file=sys.stderr)
            return 2
        print(f"Source: {args.source_id}")
        print(f"  records      : {len(records)}")
        print(f"  category     : {provenance.allowlist_category}")
        print(f"  consent basis: {provenance.licence_or_consent_basis[:80]}...")
        levels: dict[str, int] = {}
        for record in records:
            levels[record.competition_level or "(unstated)"] = (
                levels.get(record.competition_level or "(unstated)", 0) + 1
            )
        print(f"  levels       : {levels}")
        sports: dict[str, int] = {}
        for record in records:
            sports[record.sport or "(unstated)"] = sports.get(record.sport or "(unstated)", 0) + 1
        print(f"  sports       : {sports}")
        timed = sum(1 for r in records if r.time_to_competition_days is not None)
        print(f"  with timing  : {timed}/{len(records)}")
        print("\n  Target for a usable gold set: 40-50 donations (docs/recruitment.md).")
        return 0

    if args.add is None:
        parser.error("give --add <inbox.jsonl>, --template, or --verify-only")

    if not args.add.is_file():
        print(f"ERROR: {args.add} not found. Run --template first.", file=sys.stderr)
        return 2

    entries: list[dict[str, Any]] = []
    for line_no, line in enumerate(args.add.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"ERROR: {args.add}:{line_no} is not valid JSON: {exc}", file=sys.stderr)
            return 2

    print(f"A3 donation ingestion -- {len(entries)} entries from {args.add}")

    accepted: list[RawRecord] = []
    refused = 0
    for index, entry in enumerate(entries, 1):
        reason = _check(entry, args.source_id, index)
        if reason:
            refused += 1
            code = reason.split(":", 1)[0]
            log_refusal(code, args.source_id, reason)
            print(f"  REFUSED entry {index}: {reason}")
            continue
        accepted.append(_to_record(entry, args.source_id, index))

    if not accepted:
        print(
            f"\n  No donation passed the consent and content gates "
            f"({refused} refused). Nothing written.",
            file=sys.stderr,
        )
        return 1

    try:
        with store.open_source(
            a3_descriptor(args.source_id, collection_date=date.today().isoformat())
        ) as writer:
            for record in accepted:
                writer.write(record)
    except IngestionRefused as exc:
        print(f"\nREFUSED: {exc}", file=sys.stderr)
        return 2

    print(f"\n  accepted {len(accepted)}, refused {refused}")
    print(f"  written to data/raw/{args.source_id}/")
    print("\n  NEXT: de-identify before anything reads this text.")
    print("    python scripts/run_preprocessing.py")
    print(f"    python scripts/run_donation.py --verify-only --source-id {args.source_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
