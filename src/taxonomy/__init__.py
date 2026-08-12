"""Phase 12 -- label validation and taxonomy refinement.

Three modules, one per half of the freeze criterion plus the record it leaves:

    burden      what annotation costs a person, and what dropping a construct
                returns (OPEN-026)
    refinement  what *kind* of disagreement each construct attracts, and the
                repair that kind implies
    versioning  the v2->v3 diff, the changelog, and the silver re-labelling a
                proposed change invalidates

`config/taxonomy.yaml` freezes the construct set at Phase 12 *"after checking
annotation burden and inter-annotator agreement."* Phase 11 supplied agreement.
Nothing here edits the taxonomy: every output is a recommendation to the owner
(`CLAUDE.md` sec.10), because a construct set a script can quietly shrink is not
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
from .refinement import (
    KAPPA_MODERATE,
    KAPPA_SUBSTANTIAL,
    VERDICT_DROP_CANDIDATE,
    VERDICT_KEEP,
    VERDICT_MERGE_CANDIDATE,
    VERDICT_REVISE_INTENSITY_ANCHORS,
    VERDICT_REVISE_RUBRIC,
    VERDICT_REVISE_SPAN_RULE,
    VERDICT_UNDER_SAMPLED,
    ConstructVerdict,
    DisagreementProfile,
    RefinementReport,
    analyse,
    confusion_pairs,
    profile_disagreements,
    verdict_for,
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
    "KAPPA_MODERATE",
    "KAPPA_SUBSTANTIAL",
    "VERDICT_DROP_CANDIDATE",
    "VERDICT_KEEP",
    "VERDICT_MERGE_CANDIDATE",
    "VERDICT_REVISE_INTENSITY_ANCHORS",
    "VERDICT_REVISE_RUBRIC",
    "VERDICT_REVISE_SPAN_RULE",
    "VERDICT_UNDER_SAMPLED",
    "BurdenReport",
    "Changelog",
    "ConstructBurden",
    "ConstructVerdict",
    "DisagreementProfile",
    "RefinementReport",
    "RelabelScope",
    "TaxonomyChange",
    "TaxonomyVersionError",
    "TimingModel",
    "analyse",
    "confusion_pairs",
    "diff_taxonomy",
    "estimate_burden",
    "profile_disagreements",
    "relabel_scope",
    "verdict_for",
]
