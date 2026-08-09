"""Allow-list enforcement -- the gate every source must pass before ingestion.

This module is the code form of `docs/ethics.md` sec.3 and its machine-readable
companion `config/data_sources_allowlist.yaml`. Phase 5 wrote the policy; this
is where the policy stops being a document and starts being a control.

Design principle, taken verbatim from the config file: **fail closed**. An
unlisted source is denied. A category whose status is not exactly `permitted` is
denied. A source matching any prohibition is denied. There is deliberately no
`--force`, no `allow_unlisted=True`, and no environment variable that relaxes
any of this. The config file says "Never add a bypass flag to this checking
path", and that instruction is honoured here.

This mirrors the taxonomy guardrail in `src/agents/crew.py`: a rule that lives
only in a prompt or a comment is a suggestion, and a rule that lives in a check
is a rule.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = REPO_ROOT / "config" / "data_sources_allowlist.yaml"
REFUSAL_LOG_PATH = REPO_ROOT / "logs" / "ingestion_refusals.log"


class IngestionRefused(RuntimeError):
    """Raised when a source or record is refused by policy.

    Deliberately an error rather than a warning-and-skip. A refusal that only
    warns produces a corpus that is quietly missing records, and nobody notices
    until the dataset section of the paper does not add up.
    """

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"[{reason_code}] {message}")


class AllowlistError(RuntimeError):
    """Raised when the allow-list config itself is missing or malformed."""


@dataclass(frozen=True)
class Category:
    """One permitted category (A1-A4) as declared in the allow-list."""

    key: str
    primary: bool
    description: str
    requires: tuple[str, ...]
    redistribution: str
    status: str
    notes: str

    @property
    def is_permitted(self) -> bool:
        return self.status == "permitted"


@dataclass(frozen=True)
class Prohibition:
    """One prohibited practice (P1-P7)."""

    id: str
    rule: str
    reason: str


@dataclass(frozen=True)
class Allowlist:
    """The parsed, validated policy.

    Loaded once and passed explicitly to everything that needs it, rather than
    read from disk at each call site. That makes the tests able to hand in a
    synthetic policy without monkeypatching a module global.
    """

    version: int
    default_action: str
    policy_document: str
    categories: dict[str, Category]
    prohibitions: tuple[Prohibition, ...]
    provenance_required_fields: tuple[str, ...]
    provenance_optional_fields: tuple[str, ...]
    enforcement: dict[str, str]

    def category(self, key: str) -> Category | None:
        return self.categories.get(key)

    def permitted_category_keys(self) -> tuple[str, ...]:
        return tuple(k for k, c in self.categories.items() if c.is_permitted)


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise AllowlistError(f"missing required key {key!r} in {where}")
    return mapping[key]


def load_allowlist(path: Path | None = None) -> Allowlist:
    """Load and validate `config/data_sources_allowlist.yaml`.

    Validation is strict and happens here, at load time, for the same reason
    `src/agents/config.py` validates routing at load time: a typo in a policy
    file should stop the run immediately, not surface as a permissive default
    three calls deep.
    """
    path = path or ALLOWLIST_PATH
    if not path.exists():
        raise AllowlistError(f"allow-list not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AllowlistError(f"{path} did not parse to a mapping")

    default_action = str(raw.get("default_action", "deny"))
    if default_action != "deny":
        # A permissive default would silently admit every source we forgot to
        # list. If someone ever changes this, the run should stop, loudly.
        raise AllowlistError(
            f"default_action must be 'deny' (fail closed), got {default_action!r}. "
            "Refusing to load a policy that admits unlisted sources by default."
        )

    permitted_raw = _require(raw, "permitted", str(path))
    if not isinstance(permitted_raw, dict) or not permitted_raw:
        raise AllowlistError(f"{path}: 'permitted' must be a non-empty mapping")

    categories: dict[str, Category] = {}
    for key, body in permitted_raw.items():
        if not isinstance(body, dict):
            raise AllowlistError(f"{path}: permitted.{key} must be a mapping")
        categories[key] = Category(
            key=key,
            primary=bool(body.get("primary", False)),
            description=str(body.get("description", "")).strip(),
            requires=tuple(body.get("requires", ())),
            redistribution=str(body.get("redistribution", "")).strip(),
            status=str(body.get("status", "")).strip(),
            notes=str(body.get("notes", "")).strip(),
        )

    prohibited_raw = raw.get("prohibited", [])
    if not isinstance(prohibited_raw, list):
        raise AllowlistError(f"{path}: 'prohibited' must be a list")
    prohibitions = tuple(
        Prohibition(
            id=str(_require(p, "id", "prohibited[]")),
            rule=str(p.get("rule", "")).strip(),
            reason=str(p.get("reason", "")).strip(),
        )
        for p in prohibited_raw
    )

    required = tuple(raw.get("provenance_required_fields", ()))
    if not required:
        raise AllowlistError(f"{path}: provenance_required_fields must be non-empty")

    return Allowlist(
        version=int(raw.get("version", 0)),
        default_action=default_action,
        policy_document=str(raw.get("policy_document", "docs/ethics.md")),
        categories=categories,
        prohibitions=prohibitions,
        provenance_required_fields=required,
        provenance_optional_fields=tuple(raw.get("provenance_optional_fields", ())),
        enforcement={str(k): str(v) for k, v in (raw.get("enforcement") or {}).items()},
    )


# ---------------------------------------------------------------------------
# Refusal logging
# ---------------------------------------------------------------------------


def log_refusal(
    reason_code: str,
    source_id: str,
    detail: str,
    log_path: Path | None = None,
) -> None:
    """Append one refusal to `logs/ingestion_refusals.log`.

    The allow-list names this file as `enforcement.log_destination`. A refusal
    that is raised but not recorded leaves no evidence that the control fired,
    and "the pipeline refused nothing" is indistinguishable from "the pipeline
    never checked" without a log.
    """
    path = log_path or REFUSAL_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")
    line = f"{stamp}\t{reason_code}\t{source_id}\t{detail}\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)


def refuse(
    reason_code: str,
    source_id: str,
    detail: str,
    log_path: Path | None = None,
) -> None:
    """Log a refusal and raise. The only way this module says no."""
    log_refusal(reason_code, source_id, detail, log_path=log_path)
    raise IngestionRefused(reason_code, f"source {source_id!r}: {detail}")


# ---------------------------------------------------------------------------
# The checks themselves
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceDescriptor:
    """What a caller claims about a source, before anything is believed.

    Every field here is an assertion by the person wiring up the source. The
    checks below decide whether the assertions are internally consistent and
    permitted. Nothing in this dataclass is trusted on its own.
    """

    source_id: str
    source_name: str
    allowlist_category: str
    url_or_citation: str
    licence_or_consent_basis: str
    permitted_uses: str
    redistribution_permitted: bool
    synthetic: bool
    subject_is_adult: bool
    language: str
    notes: str = ""
    collection_date: str | None = None  # ISO date; defaults to today at write time

    # Source-level defaults for the optional, time-aware fields. Per-record
    # values override these. See records.RawRecord.
    sport: str | None = None
    competition_level: str | None = None
    region: str | None = None
    source_type: str | None = None
    time_to_competition_days: int | None = None

    # Declared prohibition self-checks. The harvester asserts these; the checker
    # verifies the assertions are present and negative before admitting anything.
    declares: dict[str, bool] = field(default_factory=dict)


#: Assertions a caller must make explicitly, mapped to the prohibition each one
#: guards. Written as a positive claim ("this is NOT X") so that a caller who
#: forgets a key is refused rather than defaulted into compliance.
REQUIRED_DECLARATIONS: dict[str, str] = {
    "not_scraped_personal_social_media": "P1_social_media_scraping",
    "no_minors": "P2_minors",
    "not_private_communication": "P3_private_communications",
    "licence_and_tos_permit_this_use": "P4_licence_or_tos_violation",
    "not_behind_auth_or_paywall": "P5_authenticated_or_paywalled_scraping",
    "not_health_injury_or_treatment_content": "P6_health_content",
    "provenance_is_complete": "P7_unverifiable_provenance",
}


def check_source(
    descriptor: SourceDescriptor,
    allowlist: Allowlist,
    *,
    log_path: Path | None = None,
) -> Category:
    """Decide whether a source may be ingested. Returns its category or raises.

    Order matters. Category existence is checked before category status, and
    both before the prohibition sweep, so the refusal log records the most
    specific applicable reason rather than a generic one.
    """
    sid = descriptor.source_id

    if not sid or not sid.strip():
        refuse("EMPTY_SOURCE_ID", "<unnamed>", "source_id is empty", log_path=log_path)

    # 1. Is the claimed category one this project has ever permitted?
    category = allowlist.category(descriptor.allowlist_category)
    if category is None:
        refuse(
            "UNLISTED_SOURCE",
            sid,
            f"category {descriptor.allowlist_category!r} is not in the allow-list; "
            f"permitted categories are {sorted(allowlist.categories)}. "
            "default_action is deny.",
            log_path=log_path,
        )
        raise AssertionError("unreachable")  # pragma: no cover -- refuse() always raises

    # 2. Is that category currently permitted? A category can exist in the file
    #    but be pending owner confirmation or withdrawn.
    if not category.is_permitted:
        refuse(
            "CATEGORY_NOT_PERMITTED",
            sid,
            f"category {category.key!r} has status {category.status!r}, not 'permitted'",
            log_path=log_path,
        )

    # 3. Every prohibition must be explicitly declared against, and cleared.
    for declaration, prohibition_id in REQUIRED_DECLARATIONS.items():
        if declaration not in descriptor.declares:
            refuse(
                "MISSING_DECLARATION",
                sid,
                f"source does not declare {declaration!r}, which guards {prohibition_id}. "
                "Silence is not consent: declare it explicitly.",
                log_path=log_path,
            )
        if descriptor.declares[declaration] is not True:
            refuse(
                "PROHIBITED_MATCH",
                sid,
                f"{declaration!r} is not True, so the source matches {prohibition_id}",
                log_path=log_path,
            )

    # 4. Internal consistency between the descriptor and the category.
    if category.key == "A2_synthetic" and not descriptor.synthetic:
        refuse(
            "CATEGORY_MISMATCH",
            sid,
            "declared category A2_synthetic but synthetic=False",
            log_path=log_path,
        )
    if descriptor.synthetic and category.key != "A2_synthetic":
        refuse(
            "CATEGORY_MISMATCH",
            sid,
            f"synthetic=True but declared category {category.key!r}; "
            "synthetic text belongs in A2_synthetic so that it can never be "
            "presented as real athlete speech",
            log_path=log_path,
        )
    if not descriptor.subject_is_adult:
        refuse(
            "PROHIBITED_MATCH",
            sid,
            "subject_is_adult=False matches P2_minors",
            log_path=log_path,
        )
    if not str(descriptor.licence_or_consent_basis).strip():
        refuse(
            "MISSING_LICENCE_BASIS",
            sid,
            "licence_or_consent_basis is empty; docs/ethics.md sec.4 requires it "
            "recorded verbatim, not summarised",
            log_path=log_path,
        )

    return category
