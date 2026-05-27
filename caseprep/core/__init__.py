"""Shared CasePrep core contracts and facade."""

from .contracts import (
    ArtifactRef,
    BuildCasePlanRequest,
    BuildCasePlanResult,
    EvidenceRecord,
    IntentType,
    OutputIntentPlan,
    ProvenanceRecord,
)
from .engine import CasePlanBuilder, resolve_core_mode
from .errors import (
    CasePrepConfigurationError,
    CasePrepError,
    CasePrepExternalServiceError,
    CasePrepPersistenceError,
    CasePrepProvenanceError,
    CasePrepValidationError,
)

__all__ = [
    "ArtifactRef",
    "BuildCasePlanRequest",
    "BuildCasePlanResult",
    "CasePlanBuilder",
    "CasePrepConfigurationError",
    "CasePrepError",
    "CasePrepExternalServiceError",
    "CasePrepPersistenceError",
    "CasePrepProvenanceError",
    "CasePrepValidationError",
    "EvidenceRecord",
    "IntentType",
    "OutputIntentPlan",
    "ProvenanceRecord",
    "resolve_core_mode",
]
