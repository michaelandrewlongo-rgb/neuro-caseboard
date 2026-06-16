"""The eight-surface case-dossier taxonomy (LOOP_PROMPT §0).

Pure data: the ordered case sections, their headings/intros, and a **generalizable slot
vocabulary** (concept labels — the documented `ontology.py` carve-out, never clinical answers).
`compile_case_dossier` (compile.py) and the case-section author (case_author.py) both read from
here, so the taxonomy is defined in exactly one place.

Operative Plan (`04-operative-plan.md`) and Risks (`05-risk-and-rescue.md`) reuse the existing
build target files verbatim, so the case path is additive — the 3-section `build` path is
untouched. The five new surfaces and a Case-Figures band (populated in WS-4) are added beside them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CaseSection:
    target_file: str
    heading: str
    intro: str
    slots: tuple[str, ...]          # generalizable concept labels (source of compiler_slot)


# caseprep's operative/risk slot keys, reused verbatim for the shared sections.
_OPERATIVE_SLOTS = (
    "positioning", "exposure", "critical_steps", "decision_points", "stop_points",
    "closure_reconstruction", "monitoring", "equipment_adjuncts",
    "attending_preferences_questions",
)
_RISK_SLOTS = ("likely_complications", "catastrophic_complications", "mitigation",
               "rescue_triggers")


CASE_SECTIONS: list[CaseSection] = [
    CaseSection(
        "01-clinical-summary.md", "Clinical Summary",
        "The case in tight prose, normalized from the dictation.",
        ("presentation", "key_findings", "working_diagnosis", "functional_baseline")),
    CaseSection(
        "02-clinical-reasoning.md", "Clinical Reasoning",
        "Why this operation, why now — the indication logic and the evidence behind it.",
        ("indication", "timing", "evidence_basis", "natural_history")),
    CaseSection(
        "04-operative-plan.md", "Operative Plan",
        "The plan of attack: positioning, approach, critical steps, decision points, stop criteria.",
        _OPERATIVE_SLOTS),
    CaseSection(
        "06-alternatives.md", "Alternatives",
        "Other viable strategies (incl. non-operative) and the trade-off that decides.",
        ("nonoperative_option", "alternative_approach", "tradeoff")),
    CaseSection(
        "05-risk-and-rescue.md", "Risks",
        "Expected and catastrophic complications, case-specific, with rescue sequences.",
        _RISK_SLOTS),
    CaseSection(
        "07-preop-optimization.md", "Pre-op Optimization",
        "Concrete, actionable steps to reduce this case's risks before the patient is on the table.",
        ("medical_optimization", "imaging_and_planning", "consent_counseling", "team_readiness")),
    CaseSection(
        "08-surgical-technique.md", "Surgical Technique",
        "A deeper, step-by-step technique plan with the named adjuncts/maneuvers and rescue sequences.",
        ("approach_corridor", "key_steps", "named_adjuncts", "rescue_sequence")),
    CaseSection(
        "09-case-figures.md", "Case Figures",
        "Generated schematics that help conceptualize this exact case (corridor, trajectory, level).",
        ("schematic",)),
]

CASE_ORDER = [s.target_file for s in CASE_SECTIONS]
CASE_HEADINGS = {s.target_file: s.heading for s in CASE_SECTIONS}
CASE_INTROS = {s.target_file: s.intro for s in CASE_SECTIONS}
# section_key -> legal section file (validation, mirrors explore_llm._SLOTS_BY_FILE)
SLOTS_BY_FILE = {s.target_file: s.slots for s in CASE_SECTIONS}
# section_key -> Title Case compiler_slot label
SLOT_LABEL = {k: k.replace("_", " ").title()
              for s in CASE_SECTIONS for k in s.slots}
