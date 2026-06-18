"""Case-section author — `CaseContext` -> a `QuestionManifest` across the 8 case surfaces.

LLM-first, mirroring the Explorer (`explore_llm.py`) and the intake layer: the model call is
**injected** (`complete_fn`) so parse/validate is testable offline and deterministic, and any
failure degrades to a grounded deterministic scaffold that still covers every section. The
deterministic path is **topic-agnostic** — it composes from the case's own fields + generalizable
process labels (the documented `ontology.py` carve-out), and reuses caseprep's topic-driven
generator for the Operative Plan / Risks surfaces. No hardcoded clinical content lives here.

WS-2 of the case-dossier engine. The anti-bleed guard (`guard.prune_offtarget`) is applied by the
pipeline (`build_case_dossier`), not here, so this module stays a pure author.
"""

from __future__ import annotations

import json
import os

from caseprep.explorer.question_manifest import QuestionCard, QuestionManifest

from neuro_caseboard.case_context import CaseContext
from neuro_caseboard.case_sections import CASE_ORDER, SLOTS_BY_FILE, SLOT_LABEL
from neuro_caseboard.explore_llm import _extract_json, _default_complete, llm_available

_OPERATIVE = "04-operative-plan.md"
_RISK = "05-risk-and-rescue.md"
_MIN_CASE_CARDS = 6   # below this the LLM author is treated as failed -> deterministic fallback

CASE_SYSTEM = """You are a fellowship-trained attending neurosurgeon authoring a pre-operative \
CASE DOSSIER for ONE specific patient, from a structured case context. Write declarative, \
case-specific cards across these eight sections (use the exact target_file + section_key):

- 01-clinical-summary.md: presentation, key_findings, working_diagnosis, functional_baseline
- 02-clinical-reasoning.md: indication, timing, evidence_basis, natural_history
- 04-operative-plan.md: positioning, exposure, critical_steps, decision_points, stop_points, \
closure_reconstruction, monitoring, equipment_adjuncts, attending_preferences_questions
- 06-alternatives.md: nonoperative_option, alternative_approach, tradeoff
- 05-risk-and-rescue.md: likely_complications, catastrophic_complications, mitigation, rescue_triggers
- 07-preop-optimization.md: medical_optimization, imaging_and_planning, consent_counseling, team_readiness
- 08-surgical-technique.md: approach_corridor, key_steps, named_adjuncts, rescue_sequence
- 09-case-figures.md: schematic

Rules: STATE the fact as an assertion the surgeon will confirm — do not quiz. Make every card \
specific to THIS case (its side/level/pathology/goal/comorbidities). Do NOT invent a specific you \
are unsure of — hedge to a correct general statement instead (a wrong named vessel is worse than a \
general one). Do NOT include content from a different operation or subspecialty. Cover EVERY \
section, and within each section EVERY listed facet (section_key above), with at least one card — \
the per-section facet list is your completeness checklist.

COMPLETENESS — be exhaustive; a sparse dossier fails. Emit MULTIPLE cards per section (aim for \
20-30 cards total, weighted toward Operative Plan, Risks, and Surgical Technique); never collapse \
several distinct facts into one card. Without fabricating (the anti-invention rule above still \
binds — when unsure of a specific, state the correct general structure/category), make sure the \
dossier covers, for THIS operation:
- Structures at risk: walk the WHOLE approach corridor and the target and name EVERY neural, \
vascular, and visceral structure the exposure or the resection/decompression endangers — one card \
per structure, each paired with the specific step or maneuver that puts it at risk. Include the \
structures at the periphery/poles of the lesion and along the approach, not only the obvious \
central one.
- Recognized deficits: name the specific, named post-operative neurological deficits THIS exact \
operation is known to cause (not a generic "neurological injury").
- Early postoperative emergency: identify the dominant time-critical postoperative emergency for \
this operation that threatens the airway, perfusion, or neurological status, with its concrete \
bedside / return-to-OR rescue.
- Rescue maneuvers: for each catastrophic intra-operative complication, name the specific rescue \
maneuver, adjunct, or drug used to control it.
- Reconstruction/closure: state the closure and any reconstruction / implant / graft / construct, \
including the structural goal of the reconstruction.
- Readiness & protocol: state the concrete team readiness this case needs (blood-product and \
vascular-access readiness if blood loss is expected, positioning-specific physiologic precautions, \
proactive — not reactive — medication plans, any pre-operative adjunct) and the planned \
postoperative imaging / surveillance / staging.

Output ONLY JSON: {"cards":[{"target_file":"...","section_key":"...","question":"...","why_it_matters":"..."}]}"""


def _case_user(case: CaseContext) -> str:
    lines = ["CASE CONTEXT:"]
    for label, val in (
        ("age", case.age), ("sex", case.sex), ("laterality", case.laterality),
        ("level", case.level), ("location", case.location), ("pathology", case.pathology),
        ("procedure", case.procedure), ("surgical_goal", case.surgical_goal),
        ("presentation", case.presentation), ("imaging", case.imaging),
        ("comorbidities", ", ".join(case.comorbidities)),
        ("medications", ", ".join(case.medications)),
        ("prior_surgery", case.prior_surgery), ("functional_status", case.functional_status),
        ("constraints", ", ".join(case.constraints)),
    ):
        if val:
            lines.append(f"- {label}: {val}")
    return "\n".join(lines)


def _card(tf: str, key: str, question: str, why: str) -> QuestionCard:
    return QuestionCard(target_file=tf, section_key=key, question=question.strip(),
                        why_it_matters=why.strip(), compiler_slot=SLOT_LABEL[key],
                        answerability="needs_patient_fact")


def _coerce_case_cards(raw: dict) -> list[QuestionCard]:
    cards: list[QuestionCard] = []
    for item in raw.get("cards", []):
        try:
            tf = str(item.get("target_file", "")).strip()
            key = str(item.get("section_key", "")).strip()
            q = str(item.get("question", "")).strip()
            w = str(item.get("why_it_matters", "")).strip()
        except Exception:
            continue
        slots = SLOTS_BY_FILE.get(tf)
        if not slots or key not in slots:      # invalid file or cross-section key
            continue
        if not q or not w:
            continue
        cards.append(_card(tf, key, q, w))
    return cards


def deterministic_case_manifest(case: CaseContext) -> QuestionManifest:
    """Grounded, topic-agnostic scaffold covering all eight sections.

    Clinical Summary echoes the case's own data; Reasoning/Alternatives/Pre-op/Technique/Figures
    compose generic process prompts around the case fields; Operative Plan/Risks reuse caseprep's
    topic-driven deterministic generator (filtered to those two files). Every card is a
    clinician-verify prompt — exactly how the offline `build` path already behaves.
    """
    proc = case.procedure or "the planned operation"
    path = case.pathology or "the working diagnosis"
    topic = case.to_topic()
    target = case.target() or "the operative site"

    cards: list[QuestionCard] = []

    # 01 Clinical Summary — grounded in the case's own data (no invention).
    cards.append(_card("01-clinical-summary.md", "presentation",
                       case.presentation or f"Summarize the clinical presentation for {topic}.",
                       "Anchors the dossier to this patient."))
    # WS-3: the facet checklist is the section's slot vocabulary — cover EVERY facet, even when the
    # case data is sparse, with a generic (non-fabricating) prompt rather than dropping the card.
    cards.append(_card("01-clinical-summary.md", "key_findings",
                       (f"Key imaging/exam finding: {case.imaging}" if case.imaging
                        else f"State the key imaging and exam findings for {topic}."),
                       "Defines the operative target."))
    cards.append(_card("01-clinical-summary.md", "working_diagnosis",
                       f"Working diagnosis: {path}.", "Frames the operative question."))
    cards.append(_card("01-clinical-summary.md", "functional_baseline",
                       (f"Functional baseline: {case.functional_status}" if case.functional_status
                        else f"State the functional baseline relevant to {topic}."),
                       "Sets the goal and risk tolerance."))

    # 02 Clinical Reasoning — generic indication logic composed from the case.
    cards += [
        _card("02-clinical-reasoning.md", "indication",
              f"Confirm the indication for {proc} given {path}.",
              "Establishes why this operation."),
        _card("02-clinical-reasoning.md", "timing",
              f"Confirm why operate now versus continued observation for {path}.",
              "Establishes why now."),
        _card("02-clinical-reasoning.md", "evidence_basis",
              f"Identify the evidence basis supporting {proc} for {path}.",
              "Grounds the recommendation in evidence."),
        _card("02-clinical-reasoning.md", "natural_history",
              f"Confirm the expected natural history of {path} without operation.",
              "Sets the comparison for the decision."),
    ]

    # 06 Alternatives — non-operative and alternative approaches with the trade-off.
    cards += [
        _card("06-alternatives.md", "nonoperative_option",
              f"Consider non-operative management as an alternative to {proc}.",
              "A real alternative must be weighed."),
        _card("06-alternatives.md", "alternative_approach",
              f"Consider alternative operative approaches to {target}.",
              "Approach choice changes the risk profile."),
        _card("06-alternatives.md", "tradeoff",
              f"State the trade-off that selects {proc} over the alternatives.",
              "Makes the decision explicit and defensible."),
    ]

    # 07 Pre-op Optimization — per-comorbidity + planning/consent/team readiness.
    for com in case.comorbidities:
        cards.append(_card("07-preop-optimization.md", "medical_optimization",
                           f"Optimize {com} before surgery.",
                           "Reduces a case-specific peri-operative risk."))
    if not case.comorbidities:
        cards.append(_card("07-preop-optimization.md", "medical_optimization",
                           "Optimize the relevant medical comorbidities before surgery.",
                           "Reduces peri-operative risk."))
    cards += [
        _card("07-preop-optimization.md", "imaging_and_planning",
              f"Confirm the imaging and operative planning needed before {proc}.",
              "Avoids day-of surprises."),
        _card("07-preop-optimization.md", "consent_counseling",
              f"Counsel on the case-specific risks and expected recovery for {proc}.",
              "Informed consent and expectations."),
        _card("07-preop-optimization.md", "team_readiness",
              "Brief the anesthesia and nursing team on what to have ready "
              "(blood products, drugs, monitoring, devices).",
              "Shared readiness shortens recognition-to-rescue time."),
    ]

    # 08 Surgical Technique — corridor, steps, adjuncts, rescue (composed from the case).
    cards += [
        _card("08-surgical-technique.md", "approach_corridor",
              f"Define the approach corridor for {topic}.",
              "The corridor dictates exposure and what is at risk."),
        _card("08-surgical-technique.md", "key_steps",
              f"Rehearse the key operative steps of {proc} in order.",
              "A rehearsed sequence reduces intra-operative error."),
        _card("08-surgical-technique.md", "named_adjuncts",
              f"Confirm the intra-operative adjuncts and monitoring to have ready for {proc}.",
              "The right adjuncts must be set up in advance."),
        _card("08-surgical-technique.md", "rescue_sequence",
              f"Rehearse the rescue sequence for the dominant catastrophic complication of {proc}.",
              "Rescue is faster when pre-planned."),
    ]

    # 09 Case Figures — what schematics to prepare (WS-4 generates them).
    cards.append(_card("09-case-figures.md", "schematic",
                       f"Prepare case schematics: the operative corridor/trajectory and "
                       f"{target} anatomy for {topic}.",
                       "A case-specific schematic aids conceptualization."))

    # 04 Operative Plan + 05 Risks — reuse caseprep's topic-driven deterministic generator,
    # filtered to those two files; with a minimal scaffold floor so the sections are never empty.
    cards += [
        _card(_OPERATIVE, "critical_steps", f"Rehearse the critical steps of {proc}.",
              "The operative spine of the case."),
        _card(_OPERATIVE, "decision_points", "Identify the key intra-operative decision points.",
              "Pre-decided branch points reduce hesitation."),
        _card(_OPERATIVE, "stop_points", "Define the stop criteria for this operation.",
              "Knowing when to stop prevents harm."),
        _card(_RISK, "likely_complications", f"Enumerate the likely complications of {proc}.",
              "Anticipation enables prevention."),
        _card(_RISK, "catastrophic_complications",
              f"Identify the catastrophic complications of {proc} and their rescue.",
              "The low-frequency, high-stakes events."),
        _card(_RISK, "mitigation", "State the mitigation for each identified complication.",
              "Mitigation is the actionable half of risk."),
    ]
    try:
        from neuro_caseboard.pipeline import _deterministic_manifest, classify_profile
        base = _deterministic_manifest(topic, classify_profile(topic))
        # Reuse caseprep's topic-driven Operative-Plan/Risks cards, but skip any (file, key) we
        # already authored above with a topic-agnostic card. caseprep's GENERIC templates can carry
        # hardcoded cross-subspecialty enumerations (e.g. a catch-all "abort: VA/carotid bleeding…"
        # stop-points line) that bleed into an off-axis case and that the posterior-only anti-bleed
        # guard does not catch; our own cards for those keys are topic-agnostic by construction.
        have = {(c.target_file, c.section_key) for c in cards}
        for c in base.cards:
            if c.target_file in (_OPERATIVE, _RISK) and (c.target_file, c.section_key) not in have:
                cards.append(c)
                have.add((c.target_file, c.section_key))
    except Exception:
        pass

    return QuestionManifest(procedure_family="case_deterministic", cards=cards)


def _provider_complete():
    """Bind to the live provider dispatch when configured and not disabled, else None."""
    if os.environ.get("CASEBOARD_LLM", "1") == "0":
        return None
    if not llm_available():
        return None
    return lambda system, user: _default_complete(system, user, temperature=0.2)


# Sections the author itself must populate. The Case-Figures band (09) is filled by figures_gen
# downstream, not by the manifest, so it is excluded; the literature lane only attaches to sections
# that already exist, never creates one.
_AUTHORED_SECTIONS = tuple(tf for tf in CASE_ORDER if tf != "09-case-figures.md")


def _ensure_section_coverage(cards: list[QuestionCard], case: CaseContext) -> list[QuestionCard]:
    """Guarantee every author-owned section has at least one card. `compile._compile` drops any
    section with no claims/figures, so a live author that returns enough cards but clusters them in
    a few files (e.g. only Operative Plan + Risks) would silently ship an incomplete dossier. Rather
    than discard the good LLM cards via a blunt full fallback, backfill only the *missing* sections
    from the grounded, topic-agnostic deterministic scaffold."""
    covered = {c.target_file for c in cards}
    missing = [tf for tf in _AUTHORED_SECTIONS if tf not in covered]
    if not missing:
        return cards
    by_file: dict[str, list[QuestionCard]] = {}
    for c in deterministic_case_manifest(case).cards:
        by_file.setdefault(c.target_file, []).append(c)
    for tf in missing:
        cards.extend(by_file.get(tf, []))
    return cards


def build_case_manifest(case: CaseContext, *, complete_fn=None, retries: int = 1) -> QuestionManifest:
    """Author a case manifest across the 8 surfaces. LLM-first (injected ``complete_fn`` or a
    configured provider); on no-provider, repeated underproduction, or repeated failure, the
    deterministic scaffold. Always returns a manifest covering every section.

    A single transient model hiccup (a parse error or a short reply) should NOT silently degrade
    the dossier to the generic deterministic scaffold, so the live call is retried ``retries`` times
    before falling back — the live grade showed one such transient failure tanking a case."""
    fn = complete_fn or _provider_complete()
    if fn is None:
        return deterministic_case_manifest(case)
    for _ in range(retries + 1):
        try:
            cards = _coerce_case_cards(json.loads(_extract_json(fn(CASE_SYSTEM, _case_user(case)))))
            if len(cards) >= _MIN_CASE_CARDS:
                cards = _ensure_section_coverage(cards, case)
                return QuestionManifest(procedure_family="case_llm", cards=cards)
        except Exception:
            pass            # transient: try again, then degrade
    return deterministic_case_manifest(case)
