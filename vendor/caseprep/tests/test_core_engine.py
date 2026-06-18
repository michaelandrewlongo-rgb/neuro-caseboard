"""Tests for the shared CasePrep core engine facade contracts."""

from __future__ import annotations

import pytest

from caseprep.core import (
    ArtifactRef,
    BuildCasePlanRequest,
    BuildCasePlanResult,
    CasePlanBuilder,
    CasePrepConfigurationError,
    CasePrepExternalServiceError,
    CasePrepValidationError,
    EvidenceRecord,
    resolve_core_mode,
)
from caseprep.adapters.caseplan import build_caseplan_request


def test_build_case_plan_request_normalizes_topic_and_output_dir(tmp_path):
    output_dir = tmp_path / "vs-caseprep"
    request = BuildCasePlanRequest(
        topic="  vestibular schwannoma  ",
        output_dir=output_dir,
        max_per_category=4,
        profile_hint="skull_base",
        structured_output=True,
    )

    assert request.topic == "vestibular schwannoma"
    assert request.output_dir == output_dir
    assert request.resolved_case_input() == "vestibular schwannoma"


def test_build_case_plan_request_accepts_case_input_without_topic(tmp_path):
    output_dir = tmp_path / "caseprep"
    request = BuildCasePlanRequest(
        case_input="  83F R ICA terminus aneurysm for right pterional clipping  ",
        output_dir=str(output_dir),
        max_per_category=2,
    )

    assert request.topic is None
    assert request.case_input == "83F R ICA terminus aneurysm for right pterional clipping"
    assert request.output_dir == output_dir
    assert request.resolved_case_input() == (
        "83F R ICA terminus aneurysm for right pterional clipping"
    )


def test_build_case_plan_request_topic_is_resolved_case_input_fallback():
    request = BuildCasePlanRequest(topic="  vestibular schwannoma  ")

    assert request.topic == "vestibular schwannoma"
    assert request.case_input is None
    assert request.resolved_case_input() == "vestibular schwannoma"


def test_build_case_plan_request_case_input_takes_precedence_when_present():
    request = BuildCasePlanRequest(
        topic="vestibular schwannoma",
        case_input="left retrosigmoid vestibular schwannoma resection",
    )

    assert request.resolved_case_input() == (
        "left retrosigmoid vestibular schwannoma resection"
    )


def test_build_case_plan_request_rejects_blank_topic():
    with pytest.raises(CasePrepValidationError) as exc:
        BuildCasePlanRequest(topic=" ")

    assert exc.value.code == "validation_error"
    assert exc.value.details["field"] == "topic"


def test_build_case_plan_request_rejects_blank_topic_and_case_input():
    with pytest.raises(CasePrepValidationError) as exc:
        BuildCasePlanRequest(topic=" ", case_input="\t")

    assert exc.value.code == "validation_error"
    assert exc.value.details["field"] == "topic"


def test_build_case_plan_request_from_mapping_accepts_case_input():
    request = BuildCasePlanRequest.from_mapping(
        {"case_input": "  right pterional clipping  ", "max_per_category": 1}
    )

    assert request.topic is None
    assert request.case_input == "right pterional clipping"
    assert request.resolved_case_input() == "right pterional clipping"


def test_build_case_plan_request_from_mapping_preserves_options():
    request = BuildCasePlanRequest.from_mapping(
        {
            "topic": "aneurysm",
            "options": {"include_images": False, "note": "urgent"},
        }
    )

    assert request.options == {"include_images": False, "note": "urgent"}


@pytest.mark.parametrize("invalid_value", [None, "3", 2.5, True, False])
def test_build_case_plan_request_rejects_invalid_max_per_category_types(
    invalid_value,
):
    with pytest.raises(CasePrepValidationError) as exc:
        BuildCasePlanRequest(topic="aneurysm", max_per_category=invalid_value)

    assert exc.value.details["field"] == "max_per_category"
    assert "integer" in str(exc.value)


def test_caseplan_adapter_defaults_max_per_category_to_core_default():
    request = build_caseplan_request({"topic": "aneurysm"})

    assert request.max_per_category == 3


def test_domain_errors_expose_stable_payloads():
    error = CasePrepExternalServiceError(
        "PubMed request failed",
        details={"provider": "pubmed"},
    )

    assert error.to_dict() == {
        "error": "external_service_error",
        "message": "PubMed request failed",
        "details": {"provider": "pubmed"},
    }


def test_artifact_ref_serializes_paths(tmp_path):
    artifact = ArtifactRef(
        path=tmp_path / "caseprep.yaml",
        kind="caseprep_yaml",
        media_type="application/x-yaml",
    )

    assert artifact.to_dict() == {
        "path": str(tmp_path / "caseprep.yaml"),
        "kind": "caseprep_yaml",
        "media_type": "application/x-yaml",
        "label": None,
        "metadata": {},
    }


def test_resolve_core_mode_defaults_to_core(monkeypatch):
    monkeypatch.delenv("CASEPREP_CORE_MODE", raising=False)

    assert resolve_core_mode() == "core"


@pytest.mark.parametrize("retired_mode", ["legacy", "shadow", "experimental"])
def test_resolve_core_mode_rejects_retired_modes(monkeypatch, retired_mode):
    monkeypatch.setenv("CASEPREP_CORE_MODE", retired_mode)

    with pytest.raises(CasePrepConfigurationError) as exc:
        resolve_core_mode()

    assert exc.value.details["field"] == "CASEPREP_CORE_MODE"


@pytest.mark.asyncio
async def test_case_plan_builder_defaults_to_core_builder(tmp_path):
    calls = []

    async def core_builder(request: BuildCasePlanRequest) -> BuildCasePlanResult:
        calls.append(request)
        return BuildCasePlanResult(
            topic=request.resolved_case_input(),
            markdown="# Core Case Plan\n\ncore output",
            output_dir=request.resolved_output_dir(),
            mode="core",
            evidence=[EvidenceRecord(id="pmid-1", source="pubmed", title="Trial")],
        )

    request = BuildCasePlanRequest(
        topic="glioma",
        output_dir=tmp_path / "glioma-caseprep",
        max_per_category=2,
    )
    builder = CasePlanBuilder(core_builder=core_builder)

    result = await builder.build_case_plan(request)

    assert calls == [request]
    assert result.topic == "glioma"
    assert result.markdown == "# Core Case Plan\n\ncore output"
    assert result.output_dir == tmp_path / "glioma-caseprep"
    assert result.mode == "core"
    assert [record.id for record in result.evidence] == ["pmid-1"]


@pytest.mark.asyncio
async def test_case_plan_builder_rejects_retired_build_modes():
    with pytest.raises(CasePrepConfigurationError):
        CasePlanBuilder(mode="legacy")
    with pytest.raises(CasePrepConfigurationError):
        CasePlanBuilder(mode="shadow")


@pytest.mark.asyncio
async def test_case_plan_builder_coerces_empty_result_topic_from_case_input(tmp_path):
    async def core_builder(request: BuildCasePlanRequest) -> BuildCasePlanResult:
        return BuildCasePlanResult(
            topic="",
            markdown="# Core Case Plan\n\ncore output",
            output_dir=tmp_path / "caseprep",
            mode="core",
        )

    request = BuildCasePlanRequest(case_input="right pterional clipping")
    builder = CasePlanBuilder(core_builder=core_builder)

    result = await builder.build_case_plan(request)

    assert result.topic == "right pterional clipping"


@pytest.mark.asyncio
async def test_case_plan_builder_uses_default_core_builder(monkeypatch):
    async def fake_core_builder(request):
        return BuildCasePlanResult(
            topic=request.topic,
            markdown="core diagnostic output",
            output_dir=request.resolved_output_dir(),
            mode="core",
            evidence=[
                EvidenceRecord(
                    id="pmid-1",
                    source="pubmed",
                    title="Core Evidence",
                )
            ],
            structured={"profile": {"name": "vascular"}},
        )

    import caseprep.core.engine as engine

    monkeypatch.setattr(engine, "_default_core_build_caseplan", fake_core_builder)
    builder = CasePlanBuilder()

    result = await builder.build_case_plan(BuildCasePlanRequest(topic="aneurysm"))

    assert result.mode == "core"
    assert result.markdown == "core diagnostic output"
    assert result.structured == {"profile": {"name": "vascular"}}
