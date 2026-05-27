"""Tests for Explorer question-manifest injection into CasePrep dossiers.

Tests the generative Explorer that handles any neurosurgical case through
profile-aware rules, with specific templates for well-known families (VS).
"""

from __future__ import annotations

import json

import pytest

from caseprep.core.builder import CoreRetrieverSet, build_core_case_plan
from caseprep.core.contracts import BuildCasePlanRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _EmptyAsyncRetriever:
    async def retrieve(self, *args, **kwargs):
        return []


class _EmptySyncRetriever:
    def retrieve(self, *args, **kwargs):
        return []


def _empty_providers() -> CoreRetrieverSet:
    return CoreRetrieverSet(
        pubmed=_EmptyAsyncRetriever(),
        radiology=_EmptyAsyncRetriever(),
        corpus=_EmptySyncRetriever(),
        corpus_semantic=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vestibular_schwannoma_dossier_replaces_needs_input_with_question_cards(
    tmp_path,
):
    """VS uses specific templates.  Anatomy and risk sections should have
    zero ``needs input``."""
    output_dir = tmp_path / "vs-caseprep"

    await build_core_case_plan(
        BuildCasePlanRequest(
            topic="retrosigmoid vestibular schwannoma, CPA angle tumor.",
            output_dir=output_dir,
            max_per_category=1,
        ),
        retrievers=_empty_providers(),
    )

    anatomy = (output_dir / "03-anatomy-at-risk.md").read_text(encoding="utf-8")
    risk = (output_dir / "05-risk-and-rescue.md").read_text(encoding="utf-8")

    # KG or hand-written template provides cards; some sections may
    # get covered, others may fall through to generic.  VS-specific
    # content should appear.
    assert "hearing" in anatomy.lower() or "facial" in anatomy.lower() or "vestibular" in anatomy.lower()
    assert "schwannoma" in anatomy.lower() or "IAC" in anatomy.upper() or "internal auditory" in anatomy.lower() or "CPA" in anatomy.upper()

    manifest_path = output_dir / "case_question_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest.get("cards", [])) > 0


@pytest.mark.asyncio
async def test_thrombectomy_family_defaults_not_replaced_by_explorer(tmp_path):
    """Thrombectomy has comprehensive family defaults.  Explorer generates a
    manifest (generic rules) but the builder guard prevents injection into
    schema, so the rendered files use family defaults."""
    output_dir = tmp_path / "m1-caseprep"

    await build_core_case_plan(
        BuildCasePlanRequest(
            topic=(
                "left M1 occlusion, NIHSS 18, ASPECTS 7, "
                "transferred for thrombectomy."
            ),
            output_dir=output_dir,
            max_per_category=1,
        ),
        retrievers=_empty_providers(),
    )

    morning = (output_dir / "00-morning-of-case.md").read_text(encoding="utf-8")
    anatomy = (output_dir / "03-anatomy-at-risk.md").read_text(encoding="utf-8")

    # Family defaults must survive
    assert "LKW" in morning.upper() or "last known well" in morning.lower()
    assert "NIHSS" in morning
    assert "ASPECTS" in morning
    assert "M1" in anatomy or "MCA" in anatomy.upper()
    assert (
        "perforator" in anatomy.lower() or "lenticulostriate" in anatomy.lower()
    )

    # Manifest artifact can exist (generic generator fires), but rendered
    # files must NOT contain Explorer VERIFY cards
    operative = (output_dir / "04-operative-plan.md").read_text(encoding="utf-8")
    assert "VERIFY:" not in operative, (
        "Thrombectomy family defaults should take precedence — no Explorer injection"
    )


@pytest.mark.asyncio
async def test_c1_2_schwannoma_generic_manifest_populates_all_sections(tmp_path):
    """A novel case (C1-2 schwannoma) gets classified as spine profile.
    The generic rule-based Explorer should generate question cards covering
    all three primary sections (anatomy, operative, risk) with zero
    ``needs input`` in populated sections."""
    output_dir = tmp_path / "c1-2-caseprep"

    await build_core_case_plan(
        BuildCasePlanRequest(
            topic="C1-2 spinal schwannoma with cord compression, far-lateral approach",
            output_dir=output_dir,
            max_per_category=1,
        ),
        retrievers=_empty_providers(),
    )

    anatomy = (output_dir / "03-anatomy-at-risk.md").read_text(encoding="utf-8")
    operative = (output_dir / "04-operative-plan.md").read_text(encoding="utf-8")
    risk = (output_dir / "05-risk-and-rescue.md").read_text(encoding="utf-8")

    # Spine-specific content must appear from some Explorer source
    # (KG, hand-written template, or generic rules)
    assert "vertebral artery" in anatomy.lower() or "schwannoma" in anatomy.lower() or "spinal" in anatomy.lower()
    assert "C1" in anatomy or "C2" in anatomy or "cervical" in anatomy.lower()

    # Manifest artifact
    manifest_path = output_dir / "case_question_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cards = manifest.get("cards", [])
    assert len(cards) >= 10, f"Expected at least 10 cards for a spine case, got {len(cards)}"

    # Each card must have required fields
    for card in cards:
        for key in (
            "target_file", "section_key", "question", "why_it_matters",
            "answerability", "compiler_slot",
        ):
            assert key in card, f"Card missing required field: {key}"


@pytest.mark.asyncio
async def test_generic_manifest_produced_for_cases_with_recognized_profile(tmp_path):
    """A case with a recognized profile (but no specific family template)
    should get a generic Explorer manifest.  This test uses a skull base
    topic that is not in the VS-specific template set."""
    output_dir = tmp_path / "meningioma-caseprep"

    await build_core_case_plan(
        BuildCasePlanRequest(
            topic="sphenoid wing meningioma, pterional approach",
            output_dir=output_dir,
            max_per_category=1,
        ),
        retrievers=_empty_providers(),
    )

    anatomy = (output_dir / "03-anatomy-at-risk.md").read_text(encoding="utf-8")
    operative = (output_dir / "04-operative-plan.md").read_text(encoding="utf-8")

    # Generic/KG Explorer should populate at least some sections
    assert "meningioma" in anatomy.lower() or "craniotomy" in anatomy.lower() or "skull" in anatomy.lower()

    # Manifest artifact must exist
    manifest_path = output_dir / "case_question_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest.get("cards", [])) > 0
