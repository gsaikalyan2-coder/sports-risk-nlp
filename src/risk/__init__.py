"""Phase 15 -- construct probabilities to an interpretable, calibrated risk index.

Two modules, and the split between them matters:

* `fusion` -- construct probabilities -> a 0-1 index plus a per-construct
  decomposition. Deterministic and taxonomy-grounded rather than learned, because
  no risk target exists to learn against; the signs come from
  `config/taxonomy.yaml`'s `risk_direction`, which is anchored to published
  instruments.
* `calibration` -- temperature scaling and ECE, fitted on validation and
  evaluated on test. `calibrate_risk_index` refuses: the per-construct
  probabilities are calibratable, the fused index is not, and the difference is
  the presence or absence of an observed outcome.

Pure Python plus PyYAML. No torch, no scikit-learn -- the risk layer runs in the
light Docker image and does not depend on Phase 14 having been trained. It
consumes a probability mapping from whatever source supplies one.
"""

from .calibration import (
    CalibrationReport,
    ReliabilityBin,
    RiskCalibrationUnavailable,
    apply_temperature,
    calibrate_risk_index,
    expected_calibration_error,
    fit_temperature,
    reliability_table,
)
from .fusion import (
    DEFAULT_MAGNITUDES,
    INTERPRETATION_MULTIPLIER,
    Contribution,
    Direction,
    LinearRiskScorer,
    PolarityPolicy,
    RiskScore,
    load_directions,
)

__all__ = [
    "CalibrationReport",
    "Contribution",
    "DEFAULT_MAGNITUDES",
    "Direction",
    "INTERPRETATION_MULTIPLIER",
    "LinearRiskScorer",
    "PolarityPolicy",
    "ReliabilityBin",
    "RiskCalibrationUnavailable",
    "RiskScore",
    "apply_temperature",
    "calibrate_risk_index",
    "expected_calibration_error",
    "fit_temperature",
    "load_directions",
    "reliability_table",
]
