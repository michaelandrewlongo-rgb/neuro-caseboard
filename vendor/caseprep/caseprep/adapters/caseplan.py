"""Build-caseplan adapter helpers shared by MCP and HTTP transports."""

from __future__ import annotations

import inspect
from dataclasses import replace
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from caseprep.core import (
    BuildCasePlanRequest,
    BuildCasePlanResult,
    CasePlanBuilder,
    CasePrepConfigurationError,
    CasePrepError,
    CasePrepExternalServiceError,
    CasePrepPersistenceError,
    CasePrepProvenanceError,
    CasePrepValidationError,
)


class CasePlanBuilderLike(Protocol):
    async def build_case_plan(
        self,
        request: BuildCasePlanRequest,
    ) -> BuildCasePlanResult:
        ...


BuilderFactory = Callable[[], CasePlanBuilderLike]


def slugify_caseplan_topic(topic: str) -> str:
    return topic.strip().lower().replace(" ", "-")


def _default_output_dir(arguments: Mapping[str, Any]) -> str | None:
    explicit_output_dir = arguments.get("output_dir")
    if explicit_output_dir:
        return str(explicit_output_dir)

    raw_case = arguments.get("case_input") or arguments.get("topic")
    if not isinstance(raw_case, str) or not raw_case.strip():
        return None
    return f"{slugify_caseplan_topic(raw_case)}-caseprep"


def build_caseplan_request(
    arguments: Mapping[str, Any],
) -> BuildCasePlanRequest:
    """Create a core request from transport arguments."""
    raw_options = arguments.get("options") or {}
    if not isinstance(raw_options, dict):
        raise CasePrepValidationError(
            "options must be an object",
            details={"field": "options"},
        )
    options = dict(raw_options)
    for key in ("semantic_top_n",):
        if key in arguments and key not in options:
            options[key] = arguments[key]
    arguments = dict(arguments)
    output_dir = _default_output_dir(arguments)
    return BuildCasePlanRequest.from_mapping(
        arguments | {"output_dir": output_dir, "options": options},
    )

async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def structure_request_intent(request: BuildCasePlanRequest) -> BuildCasePlanRequest:
    """Preserve explicit plan or add an LLM/heuristic intent plan."""
    if request.intent_plan:
        return request
    from caseprep.intent import structure_intent

    return replace(
        request,
        intent_plan=await structure_intent(request.resolved_case_input()),
    )


async def build_caseplan_result(
    arguments: Mapping[str, Any],
    *,
    builder_factory: BuilderFactory = CasePlanBuilder,
) -> BuildCasePlanResult:
    """Build a case plan and keep the structured result available to adapters."""
    request = build_caseplan_request(arguments)
    request = await structure_request_intent(request)
    builder = builder_factory()
    return await _maybe_await(builder.build_case_plan(request))


async def build_caseplan_markdown(
    arguments: Mapping[str, Any],
    *,
    builder_factory: BuilderFactory = CasePlanBuilder,
) -> str:
    """Build a case plan and return markdown/text transport output."""
    result = await build_caseplan_result(
        arguments,
        builder_factory=builder_factory,
    )
    return result.markdown


def caseprep_error_status(exc: CasePrepError) -> int:
    """Map domain errors to stable HTTP status codes."""
    if isinstance(exc, CasePrepValidationError):
        return 400
    if isinstance(exc, CasePrepProvenanceError):
        return 422
    if isinstance(exc, CasePrepExternalServiceError):
        return 503
    if isinstance(exc, (CasePrepConfigurationError, CasePrepPersistenceError)):
        return 500
    return 500


def _primary_artifact_label(result: BuildCasePlanResult) -> str | None:
    intent_type = result.intent_plan.intent_type if result.intent_plan else None
    if intent_type == "literature_review":
        return "literature_review.md"
    if intent_type == "operative_briefing":
        return "case_board.md"
    return None


def _read_primary_artifact(result: BuildCasePlanResult) -> tuple[str, dict[str, Any] | None]:
    label = _primary_artifact_label(result)
    if label is None:
        return result.markdown, None
    for artifact in result.artifacts:
        if artifact.label != label:
            continue
        try:
            summary = artifact.path.read_text(encoding="utf-8")
        except OSError:
            return result.markdown, None
        primary = artifact.to_dict()
        primary["primary"] = True
        return summary, primary
    return result.markdown, None


def caseplan_api_payload(
    result: BuildCasePlanResult,
    *,
    slug: str,
    output_dir: str,
    caseplan_id: int,
) -> dict[str, Any]:
    """Return the stable FastAPI /api/build response payload."""
    summary, primary_artifact = _read_primary_artifact(result)
    return {
        "slug": slug,
        "topic": result.topic,
        "output_dir": output_dir,
        "summary": summary,
        "caseplan_id": caseplan_id,
        "intent": result.intent_plan.to_dict() if result.intent_plan else None,
        "primary_artifact": primary_artifact,
        "artifacts": [artifact.to_dict() for artifact in result.artifacts],
        "warnings": result.warnings,
    }
