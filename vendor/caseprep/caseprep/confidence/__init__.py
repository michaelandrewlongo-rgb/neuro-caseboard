"""Token-probability confidence scoring for CasePrep compiler slots."""

from caseprep.confidence.logprobs import (
    compute_entropy,
    content_token_logprobs,
    extract_logprobs,
)

__all__ = [
    "should_refine",
    "build_refinement_prompt",
    "entropy_guided_fill",
    "extract_logprobs", "compute_entropy", "content_token_logprobs",
    "CALIBRATION_DIR", "log_calibration_point", "load_calibration_points"]
