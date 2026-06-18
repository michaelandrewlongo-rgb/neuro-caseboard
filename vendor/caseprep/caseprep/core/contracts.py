from __future__ import annotations
from dataclasses import dataclass, field

from pathlib import Path
from typing import Any, Literal, Optional



@dataclass(frozen=True)
class SlotConfidence:
    logprob: float
    entropy: float
    token_count: int = 0

    @property
    def normalized_confidence(self) -> float:
        if self.entropy == 0:
            return 1.0
        return 1 / (1 + math.exp(-self.logprob))

    def to_dict(self) -> dict[str, Any]:
        return {
            "logprob": self.logprob,
            "entropy": self.entropy,
            "token_count": self.token_count,
        }

import math # noqa: F401


from .errors import CasePrepValidationError

CoreMode = Literal["core"]

def _slugify_topic(topic: str) -> str:
    return topic.strip().lower().replace(" ", "-")

IntentType = Literal["operative_briefing", "literature_review"]


@dataclass(frozen=True)
class OutputIntentPlan:
    intent_type: IntentType
    subtype: str = "general"
    confidence: float = 1.0
    normalized_query: str = ""
    entities: dict[str, Any] = field(default_factory=dict)
    template_sections: list[str] = field(default_factory=list)
    retrieval_priorities: list[str] = field(default_factory=list)
    clarification_needed: bool = False
    clarification_question: str | None = None
    warnings: list[str] = field(default_factory=list)
    source: Literal["llm", "heuristic_fallback", "explicit"] = "heuristic_fallback"

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_type": self.intent_type,
            "subtype": self.subtype,
            "confidence": self.confidence,
            "normalized_query": self.normalized_query,
            "entities": self.entities,
            "template_sections": self.template_sections,
            "retrieval_priorities": self.retrieval_priorities,
            "clarification_needed": self.clarification_needed,
            "clarification_question": self.clarification_question,
            "warnings": self.warnings,
            "source": self.source,
        }


@dataclass(frozen=True)
class BuildCasePlanRequest:
    """Request to build a CasePrep plan for a topic or raw case input."""

    topic: str | None = None
    case_input: str | None = None
    output_dir: Path | str | None = None
    max_per_category: int = 3
    profile_hint: str | None = None
    structured_output: bool = False
    options: dict[str, Any] = field(default_factory=dict)
    intent_plan: OutputIntentPlan | None = None

    def __post_init__(self) -> None:
        topic = self.topic.strip() if self.topic is not None else None
        case_input = self.case_input.strip() if self.case_input is not None else None
        topic = topic or None
        case_input = case_input or None
        if topic is None and case_input is None:
            raise CasePrepValidationError(
                "topic or case_input is required",
                details={"field": "topic"},
            )
        if not isinstance(self.max_per_category, int) or isinstance(
            self.max_per_category,
            bool,
        ):
            raise CasePrepValidationError(
                "max_per_category must be an integer",
                details={"field": "max_per_category"},
            )
        if self.max_per_category < 1:
            raise CasePrepValidationError(
                "max_per_category must be at least 1",
                details={"field": "max_per_category"},
            )
        if self.intent_plan is not None and not isinstance(self.intent_plan, OutputIntentPlan):
            raise CasePrepValidationError(
                "intent_plan must be an OutputIntentPlan",
                details={"field": "intent_plan"},
            )
        object.__setattr__(self, "topic", topic)
        object.__setattr__(self, "case_input", case_input)
        if self.output_dir is not None and not isinstance(self.output_dir, Path):
            object.__setattr__(self, "output_dir", Path(self.output_dir))
        if self.profile_hint is not None:
            object.__setattr__(self, "profile_hint", self.profile_hint.strip() or None)

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> "BuildCasePlanRequest":
        intent_plan = values.get("intent_plan")
        if isinstance(intent_plan, dict):
            raise CasePrepValidationError(
                "intent_plan cannot be a dict, it must be an OutputIntentPlan object",
                details={"field": "intent_plan"},
            )
        if intent_plan is not None and not isinstance(intent_plan, OutputIntentPlan):
            raise CasePrepValidationError(
                "intent_plan must be an OutputIntentPlan object or None",
                details={"field": "intent_plan"},
            )
        return cls(
            topic=values.get("topic"),
            case_input=values.get("case_input"),
            output_dir=values.get("output_dir") or None,
            max_per_category=values.get("max_per_category", 3),
            profile_hint=values.get("profile_hint"),
            structured_output=values.get("structured_output", False),
            intent_plan=intent_plan,
            options=dict(values.get("options") or {}),
        )

    def resolved_case_input(self) -> str:
        """Return the normalized case input, falling back to topic."""
        return self.case_input or self.topic or ""

    def default_output_dir(self) -> Path:
        return Path.cwd() / f"{_slugify_topic(self.resolved_case_input())}-caseprep"

    def resolved_output_dir(self) -> Path:
        if self.output_dir is None:
            return self.default_output_dir()
        out = Path(self.output_dir)
        if not out.is_absolute():
            return Path.cwd() / out
        return out


@dataclass(frozen=True)
class EvidenceRecord:
    """Normalized evidence item consumed by synthesis and provenance."""

    id: str
    source: str
    title: str = ""
    url: str | None = None
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "text": self.text,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ProvenanceRecord:
    """Field-level provenance for generated structured output."""

    field_path: str
    source_ids: list[str] = field(default_factory=list)
    value_status: str = "generated"
    generated_by: str = "caseprep"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "source_ids": self.source_ids,
            "value_status": self.value_status,
            "generated_by": self.generated_by,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ArtifactRef:
    """Reference to an artifact produced by a CasePrep run."""

    path: Path
    kind: str
    media_type: str | None = None
    label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "kind": self.kind,
            "media_type": self.media_type,
            "label": self.label,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class BuildCasePlanResult:
    """Transport-neutral result for a built case plan."""

    topic: str
    markdown: str
    output_dir: Path | None = None
    mode: CoreMode = "core"
    artifacts: list[ArtifactRef] = field(default_factory=list)
    evidence: list[EvidenceRecord] = field(default_factory=list)
    confidence: Optional[SlotConfidence] = None
    provenance: list[ProvenanceRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    structured: dict[str, Any] = field(default_factory=dict)
    confidence_summary: dict[str, Any] = field(default_factory=dict)
    intent_plan: OutputIntentPlan | None = None


    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "markdown": self.markdown,
            "output_dir": str(self.output_dir) if self.output_dir else None,
            "mode": self.mode,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "evidence": [record.to_dict() for record in self.evidence],
            "confidence": self.confidence.to_dict() if self.confidence else None,
            "provenance": [record.to_dict() for record in self.provenance],
            "warnings": self.warnings,
            "structured": self.structured,
            "intent_plan": self.intent_plan.to_dict() if self.intent_plan else None,
        }
