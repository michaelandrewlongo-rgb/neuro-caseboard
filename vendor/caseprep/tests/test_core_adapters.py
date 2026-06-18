"""Tests for adapter routing through the CasePrep core facade."""

from __future__ import annotations

import pytest

from caseprep.core import BuildCasePlanResult, OutputIntentPlan
from caseprep.core import CasePrepValidationError


@pytest.mark.asyncio
async def test_mcp_build_caseplan_routes_through_core_facade(monkeypatch):
    import caseprep.mcp_server as mcp_server

    seen_requests = []

    class FakeBuilder:
        async def build_case_plan(self, request):
            seen_requests.append(request)
            return BuildCasePlanResult(
                topic=request.topic,
                markdown="# Case Plan\n\nfacade output",
                output_dir=request.resolved_output_dir(),
                mode="core",
            )

    monkeypatch.setattr(mcp_server, "CasePlanBuilder", FakeBuilder)

    output = await mcp_server._handle_build_caseplan({
        "topic": "  vestibular schwannoma  ",
        "max_per_category": 2,
    })

    assert output == "# Case Plan\n\nfacade output"
    assert seen_requests[0].topic == "vestibular schwannoma"
    assert seen_requests[0].output_dir.name == "vestibular-schwannoma-caseprep"
    assert seen_requests[0].max_per_category == 2


@pytest.mark.asyncio
async def test_build_caseplan_adapter_invokes_injected_builder():
    from caseprep.adapters.caseplan import build_caseplan_result

    seen_requests = []

    class FakeBuilder:
        async def build_case_plan(self, request):
            seen_requests.append(request)
            return BuildCasePlanResult(
                topic=request.topic,
                markdown="adapter output",
                output_dir=request.resolved_output_dir(),
                mode="core",
                structured={"profile": {"name": "vascular"}},
            )

    result = await build_caseplan_result(
        {
            "topic": "  aneurysm clipping  ",
            "max_per_category": 2,
            "structured_output": True,
        },
        builder_factory=FakeBuilder,
    )

    assert result.markdown == "adapter output"
    assert result.structured == {"profile": {"name": "vascular"}}
    assert seen_requests[0].topic == "aneurysm clipping"
    assert seen_requests[0].output_dir.name == "aneurysm-clipping-caseprep"
    assert seen_requests[0].max_per_category == 2
    assert seen_requests[0].structured_output is True


def test_build_caseplan_request_preserves_explicit_output_dir(tmp_path):
    from caseprep.adapters.caseplan import build_caseplan_request

    explicit = tmp_path / "explicit-case"
    request = build_caseplan_request({"topic": "aneurysm", "output_dir": explicit})

    assert request.output_dir == explicit


def test_build_caseplan_request_maps_semantic_top_n_into_options():
    from caseprep.adapters.caseplan import build_caseplan_request

    request = build_caseplan_request({"topic": "aneurysm", "semantic_top_n": 7})

    assert request.options["semantic_top_n"] == 7


def test_caseprep_error_status_maps_domain_errors():
    from caseprep.adapters.caseplan import caseprep_error_status

    assert caseprep_error_status(CasePrepValidationError("bad input")) == 400


def test_build_caseplan_request_rejects_unvalidated_intent_plan_dict():
    from caseprep.adapters.caseplan import build_caseplan_request

    intent_plan_data = {"intent_type": "operative_briefing", "subtype": "approach"}
    with pytest.raises(CasePrepValidationError):
        build_caseplan_request({"topic": "acoustic neuroma", "intent_plan": intent_plan_data})



def test_build_caseplan_request_rejects_invalid_intent_plan():
    from caseprep.adapters.caseplan import build_caseplan_request
    from caseprep.core.contracts import OutputIntentPlan

    with pytest.raises(CasePrepValidationError):
        build_caseplan_request({"topic": "acoustic neuroma", "intent_plan": {"foo": "bar"}})


def test_build_caseplan_request_preserves_explicit_intent_plan():
    from caseprep.adapters.caseplan import build_caseplan_request

    intent_plan = OutputIntentPlan(intent_type="literature_review", subtype="incidence")
    request = build_caseplan_request({"topic": "TLIF", "intent_plan": intent_plan})
    assert request.intent_plan == intent_plan


@pytest.mark.asyncio
async def test_build_caseplan_result_sends_heuristic_intent_plan_to_builder():
    from caseprep.adapters.caseplan import build_caseplan_result

    seen_requests = []

    class FakeBuilder:
        async def build_case_plan(self, request):
            seen_requests.append(request)
            return BuildCasePlanResult(
                topic=request.topic,
                markdown="adapter output",
                output_dir=request.resolved_output_dir(),
                mode="core",
                intent_plan=request.intent_plan,
            )

    result = await build_caseplan_result(
        {
            "topic": "  incidence of pseudoarthrosis after TLIF  ",
        },
        builder_factory=FakeBuilder,
    )

    assert seen_requests[0].intent_plan is not None
    assert seen_requests[0].intent_plan.intent_type == "literature_review"
    assert seen_requests[0].intent_plan.subtype == "incidence"
    assert result.intent_plan == seen_requests[0].intent_plan
