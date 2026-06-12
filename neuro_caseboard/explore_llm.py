"""LLM-backed Explorer — the clinical-depth fix.

The deterministic rule-based Explorer specialises well only where caseprep ships a
hand-written family template; everything else collapses to a generic (sometimes wrong)
board. To generalise across the breadth of neurosurgery, this module asks Claude to
generate **case-specific** anatomy/operative/risk question-cards for any procedure, with
a system prompt that demands procedure-specificity and forbids off-target content.

The model call is injected (`complete_fn`) so the parse/validate/build logic is testable
offline; the real call (`_anthropic_complete`) is used only when a key is present. Any
failure returns ``None`` so the pipeline falls back to the deterministic generator.
"""

from __future__ import annotations

import json
import os
import re

from caseprep.explorer.question_manifest import (
    QuestionCard,
    QuestionManifest,
    _ANATOMY_SLOTS,
    _OPERATIVE_SLOTS,
    _RISK_SLOTS,
)

# section_key -> compiler_slot, and which keys are legal for each section file.
_SLOTS_BY_FILE = {
    "03-anatomy-at-risk.md": _ANATOMY_SLOTS,
    "04-operative-plan.md": _OPERATIVE_SLOTS,
    "05-risk-and-rescue.md": _RISK_SLOTS,
}

DEFAULT_MODEL = os.environ.get("CASEBOARD_LLM_MODEL", "claude-opus-4-8")
_MIN_CARDS = 6  # below this we treat the generation as failed and fall back

_SYSTEM = """You are a fellowship-trained attending neurosurgeon building a pre-operative \
case board for a resident. Given ONE specific procedure, produce a comprehensive set of \
operative question-cards across exactly three sections:
- Anatomy at Risk (03-anatomy-at-risk.md): surgical corridor, landmarks, neural \
structures, arteries/perforators/veins/sinuses, functional structures, anatomic variants, no-fly zones
- Operative Plan (04-operative-plan.md): positioning, exposure, critical steps, decision \
points, stop criteria, closure/reconstruction, monitoring, equipment/adjuncts, attending preferences
- Risk and Rescue (05-risk-and-rescue.md): likely complications, catastrophic \
complications, mitigation, rescue triggers

Each card MUST be specific to THIS exact procedure and approach. Name the actual nerves, \
vessels, bony landmarks, operative steps, decision thresholds, complications, and rescue \
maneuvers that apply to this case. Write each card as a VERIFY prompt — something the \
surgeon confirms before/during the case — not a fact stated as already answered.

HARD RULES:
- Be procedure-specific. For a C5-6 ACDF, cover the recurrent laryngeal nerve, carotid \
sheath, esophagus, the interbody/plate construct, C5 palsy, and neck-hematoma airway \
rescue — NOT posterior laminectomy or C1-2 vertebral-artery anatomy.
- Do NOT include content from a DIFFERENT operation or subspecialty. A convexity \
meningioma board must not mention CPA cranial nerves, AICA/PICA, or the sigmoid sinus; a \
carotid endarterectomy board must not mention craniotomy or eloquent cortex.
- Cover every subsection listed above with at least one card; produce 15-28 cards total.
- Use precise clinical terminology.

Output ONLY JSON of the form:
{"cards": [{"target_file": "...", "section_key": "...", "question": "...", "why_it_matters": "..."}]}
where section_key is one of the exact keys for that target_file:
  03-anatomy-at-risk.md: surgical_corridor, landmarks_in_order, neural_structures, \
arteries_perforators_veins_sinuses, functional_structures, variants, no_fly_zones
  04-operative-plan.md: positioning, exposure, critical_steps, decision_points, \
stop_points, closure_reconstruction, monitoring, equipment_adjuncts, attending_preferences_questions
  05-risk-and-rescue.md: likely_complications, catastrophic_complications, mitigation, rescue_triggers"""

# JSON schema for structured outputs (enums keep the model on the contract).
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "target_file": {"type": "string",
                                    "enum": list(_SLOTS_BY_FILE.keys())},
                    "section_key": {"type": "string",
                                    "enum": sorted(set().union(*[m.keys() for m in _SLOTS_BY_FILE.values()]))},
                    "question": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                },
                "required": ["target_file", "section_key", "question", "why_it_matters"],
            },
        }
    },
    "required": ["cards"],
}


def llm_available() -> bool:
    """True when a key is configured and the SDK is importable."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return False
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False
    return True


def _anthropic_complete(system: str, user: str, *, model: str = DEFAULT_MODEL) -> str:
    """Real Claude call (used only when a key is present). Returns the JSON text block."""
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=12000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
    )
    return next(b.text for b in resp.content if b.type == "text")


def _coerce_cards(raw: dict):
    cards = []
    for item in raw.get("cards", []):
        try:
            target = str(item.get("target_file", "")).strip()
            key = str(item.get("section_key", "")).strip()
            question = str(item.get("question", "")).strip()
            why = str(item.get("why_it_matters", "")).strip()
        except Exception:
            continue
        slots = _SLOTS_BY_FILE.get(target)
        if slots is None or key not in slots:   # invalid or cross-section key
            continue
        if not question or not why:
            continue
        cards.append(QuestionCard(
            target_file=target,
            section_key=key,
            question=question,
            why_it_matters=why,
            compiler_slot=slots[key],
            answerability="needs_patient_fact",
        ))
    return cards


def build_llm_manifest(topic: str, *, complete_fn=None, model: str | None = None):
    """Generate a case-specific QuestionManifest for *topic*, or None on any failure."""
    complete_fn = complete_fn or (lambda s, u: _anthropic_complete(s, u, model=model or DEFAULT_MODEL))
    user = f"Procedure: {topic.strip()}"
    try:
        text = complete_fn(_SYSTEM, user)
        raw = json.loads(_extract_json(text))
    except Exception:
        return None
    cards = _coerce_cards(raw)
    if len(cards) < _MIN_CARDS:
        return None
    return QuestionManifest(procedure_family="llm_generated", cards=cards)


def _extract_json(text: str) -> str:
    """Tolerate a stray ```json fence or prose around the JSON object."""
    text = text.strip()
    if text.startswith("{"):
        return text
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text
