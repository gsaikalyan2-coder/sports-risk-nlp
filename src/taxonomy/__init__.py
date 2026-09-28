"""Phase 12 -- label validation and taxonomy refinement.

Two modules now, not three -- the record of the third is below:

    burden      what annotation costs a person, and what dropping a construct
                returns (OPEN-026)
    versioning  the v2->v3 diff, the changelog, and the silver re-labelling a
                proposed change invalidates

`config/taxonomy.yaml` freezes the construct set at Phase 12 *"after checking
annotation burden and inter-annotator agreement."* Only the burden half is
still computed here. By owner decision (2026-09-28, see `CLAUDE.md` sec.20-21
and `config/annotators.yaml`'s header), this project does not report
inter-annotator agreement, so the disagreement-driven analysis that used to
live in `refinement.py` (`analyse`, `ConstructVerdict`, `DisagreementProfile`,
`confusion_pairs`, `profile_disagreements`, `verdict_for`) was deleted along
with `src/annotation/agreement.py`, which supplied its only input
(`AgreementReport`/`ConstructAgreement`). A backup of the deleted module is
under `annotation/gold_dev/_backup_2026-09-28/removed_20260928/refinement.py`.
`scripts/run_taxonomy_refinement.py --refine` no longer exists as a result;
`--burden` and `--propose` are unaffected.

Nothing here writes `config/taxonomy.yaml`. The construct set is an owner
decision (`CLAUDE.md` sec.10), because a taxonomy a script can shrink is not
frozen.
"""

from .burden import (
    DEFAULT_TIMING,
    FATIGUE_HOURS_PER_ANNOTATOR,
    BurdenReport,
    ConstructBurden,
    TimingModel,
    estimate_burden,
)
from .versioning import (
    CHANGE_ADDED,
    CHANGE_COSMETIC,
    CHANGE_DEFINITION,
    CHANGE_REMOVED,
    CHANGE_VALUE_SPACE,
    Changelog,
    RelabelScope,
    TaxonomyChange,
    TaxonomyVersionError,
    diff_taxonomy,
    relabel_scope,
)

__all__ = [
    "CHANGE_ADDED",
    "CHANGE_COSMETIC",
    "CHANGE_DEFINITION",
    "CHANGE_REMOVED",
    "CHANGE_VALUE_SPACE",
    "DEFAULT_TIMING",
    "FATIGUE_HOURS_PER_ANNOTATOR",
    "BurdenReport",
    "Changelog",
    "ConstructBurden",
    "RelabelScope",
    "TaxonomyChange",
    "TaxonomyVersionError",
    "TimingModel",
    "diff_taxonomy",
    "estimate_burden",
    "relabel_scope",
]
