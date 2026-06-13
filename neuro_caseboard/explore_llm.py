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

_ANTHROPIC_DEFAULT = "claude-opus-4-8"
_OPENROUTER_DEFAULT = "openai/gpt-4o"
_MIN_CARDS = 6  # below this we treat the generation as failed and fall back


def _resolve_model(model: str | None, *, openrouter: bool) -> str:
    return (model or os.environ.get("CASEBOARD_LLM_MODEL")
            or (_OPENROUTER_DEFAULT if openrouter else _ANTHROPIC_DEFAULT))

_SYSTEM = """You are a fellowship-trained attending neurosurgeon building a pre-operative \
case board for a resident. Given ONE specific procedure, produce a COMPREHENSIVE, DENSE \
set of operative question-cards across exactly three sections:
- Anatomy at Risk (03-anatomy-at-risk.md): surgical corridor, landmarks in order, neural \
structures, arteries/perforators/veins/sinuses, functional structures, anatomic variants, no-fly zones
- Operative Plan (04-operative-plan.md): positioning, exposure, critical steps, decision \
points, stop criteria, closure/reconstruction, monitoring, equipment/adjuncts, attending preferences
- Risk and Rescue (05-risk-and-rescue.md): likely complications, catastrophic \
complications, mitigation, rescue triggers

DEPTH IS THE PRIORITY. The resident already owns a textbook; this board must read like a \
specific attending's intra-operative checklist for THIS exact case. The section_keys \
below are a MINIMUM checklist, NOT a quota — emit AS MANY cards per section_key as the \
case demands (usually several). A board with one generic card per key is a FAILURE.

Each card's `question` field STATES the specific clinical content as a concise assertion \
the surgeon will confirm, and MUST contain at least one CONCRETE specific — one of:
  - a named structure AND where it runs / what it is adherent to,
  - a named device or adjunct (e.g. neuronavigation, facial-nerve EMG, ABR, ICG \
videoangiography, micro-Doppler, external ventricular drain, ultrasonic aspirator),
  - a named drug and its role (e.g. mannitol for relaxation, adenosine for flow arrest, \
nimodipine for vasospasm, dexamethasone for peritumoral edema, tranexamic acid),
  - a numeric threshold or measurement, OR
  - a named operative maneuver or step sequence.
State the fact ("Recurrent laryngeal nerve runs in the tracheoesophageal groove; the \
right-sided course is more variable"), NOT a content-free prompt ("VERIFY the recurrent \
laryngeal nerve"). Do NOT begin cards with "VERIFY". BAN generic filler — no bare \
"positioning", "attending preferences", "confirm tool availability", "anatomical \
variants", "monitor for complications", or "stop if uncontrollable bleeding" unless made \
concretely specific to THIS procedure with the detail above.

RISK AND RESCUE must be the DEEPEST section. Enumerate the DISTINCT complications THIS \
specific operation is known for — at least 6 — never one generic line. Give EACH \
catastrophic complication its OWN card paired with a concrete, named, step-by-step rescue \
sequence (e.g. for an expanding cervical wound hematoma after ACDF: "open the wound at \
bedside, evacuate the clot, secure the airway / reintubate, then return to OR" — NOT \
"stop and assess").

HARD RULES:
- Be procedure-specific. For a C5-6 ACDF, cover the recurrent laryngeal nerve, carotid \
sheath, esophagus, the interbody/plate construct, C5 palsy, durotomy/CSF leak, and \
expanding neck-hematoma airway rescue — NOT posterior laminectomy or C1-2 vertebral-artery anatomy.
- Do NOT include content from a DIFFERENT operation or subspecialty. A convexity \
meningioma board must not mention CPA cranial nerves, AICA/PICA, or the sigmoid sinus; a \
carotid endarterectomy board must not mention craniotomy or eloquent cortex.
- Produce 26-40 cards total, distributed across all three sections, with the depth above.
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
    """True when a provider key is configured and its client lib is importable.

    OpenRouter (OpenAI-compatible gateway) is preferred when OPENROUTER_API_KEY is set;
    otherwise the first-party Anthropic API.
    """
    if os.environ.get("OPENROUTER_API_KEY"):
        try:
            import requests  # noqa: F401
            return True
        except Exception:
            return False
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        try:
            import anthropic  # noqa: F401
            return True
        except Exception:
            return False
    return False


def _openrouter_complete(system: str, user: str, *, model: str | None = None,
                         retries: int = 2) -> str:
    """OpenAI-compatible chat completion via OpenRouter. Returns the JSON message text.

    Retries transient failures (timeouts, 429, 5xx) so a single flake doesn't drop the
    whole board to the deterministic fallback.
    """
    import time
    import requests
    payload = {
        "model": _resolve_model(model, openrouter=True),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
        "max_tokens": 12000,
    }
    headers = {
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json",
        "X-Title": "neuro-caseboard",
    }
    last = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers, json=payload, timeout=180)
            if resp.status_code == 429 or resp.status_code >= 500:
                last = requests.HTTPError(f"{resp.status_code}: {resp.text[:200]}")
                raise last
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
            else:
                raise
    raise last  # pragma: no cover


def _anthropic_complete(system: str, user: str, *, model: str | None = None) -> str:
    """First-party Claude call. Returns the JSON text block."""
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=_resolve_model(model, openrouter=False),
        max_tokens=12000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
    )
    return next(b.text for b in resp.content if b.type == "text")


def _default_complete(system: str, user: str, *, model: str | None = None) -> str:
    if os.environ.get("OPENROUTER_API_KEY"):
        return _openrouter_complete(system, user, model=model)
    return _anthropic_complete(system, user, model=model)


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


_REFINE_SYSTEM = """You are the attending reviewing a resident's DRAFT pre-operative case \
board for ONE specific procedure (the draft cards are listed below). Identify the \
HIGH-YIELD, case-defining items a board for THIS exact operation MUST include but that \
are MISSING or too generic in the draft — especially: named feeding vessels and whether \
to embolize them, named perforators/veins/sinuses to preserve, named intra-operative \
adjuncts/devices (e.g. ICG videoangiography, facial-nerve EMG, ABR, external ventricular \
drain, micro-Doppler, ultrasonic aspirator, neuronavigation with brain-shift awareness), \
named drugs and their role (e.g. adenosine for flow arrest, mannitol for relaxation, \
nimodipine for vasospasm, dexamethasone for peritumoral edema, tranexamic acid), specific \
numeric thresholds, named approach choices (e.g. telovelar vs transvermian), and a named \
step-by-step rescue for EACH catastrophic complication.

Output ONLY JSON {"cards":[...]} of ADDITIONAL cards (same schema and section_keys) that \
fill these gaps. Do NOT repeat items already covered in the draft. Do NOT add content \
from a different operation or subspecialty. If the draft is already complete, output \
{"cards":[]}. Each card = {"target_file","section_key","question","why_it_matters"} using \
the exact section_keys defined for each target_file."""


def _draft_digest(cards) -> str:
    by_file: dict[str, list[str]] = {}
    for c in cards:
        by_file.setdefault(c.target_file, []).append(f"- [{c.section_key}] {c.question}")
    return "\n".join(f"{tf}:\n" + "\n".join(lines) for tf, lines in by_file.items())


def _merge_distinct(base, extra, threshold: float = 0.7):
    """Append *extra* cards that are not near-duplicates (word-overlap > threshold) of any
    card already kept — regardless of slot, so the refine pass can add depth to a slot the
    draft already touched (e.g. a second distinct catastrophic complication)."""
    merged = list(base)
    word_sets = [set(c.question.lower().split()) for c in merged]
    for card in extra:
        cw = set(card.question.lower().split())
        if not cw:
            continue
        if any(ws and len(cw & ws) / min(len(cw), len(ws)) > threshold for ws in word_sets):
            continue
        merged.append(card)
        word_sets.append(cw)
    return merged


def build_llm_manifest(topic: str, *, complete_fn=None, model: str | None = None):
    """Generate a case-specific QuestionManifest for *topic*, or None on any failure.

    Two passes when ``CASEBOARD_LLM_REFINE`` != "0" (default on): a draft pass, then an
    attending-review pass that adds case-defining items the draft missed. The refine pass
    is best-effort — any failure leaves the draft untouched."""
    complete_fn = complete_fn or (lambda s, u: _default_complete(s, u, model=model))
    user = f"Procedure: {topic.strip()}"
    try:
        text = complete_fn(_SYSTEM, user)
        raw = json.loads(_extract_json(text))
    except Exception:
        return None
    cards = _coerce_cards(raw)
    if len(cards) < _MIN_CARDS:
        return None
    if os.environ.get("CASEBOARD_LLM_REFINE", "1") != "0":
        try:
            rtext = complete_fn(_REFINE_SYSTEM, f"{user}\n\nDraft cards:\n{_draft_digest(cards)}")
            extra = _coerce_cards(json.loads(_extract_json(rtext)))
            cards = _merge_distinct(cards, extra)
        except Exception:
            pass
    return QuestionManifest(procedure_family="llm_generated", cards=cards)


def _extract_json(text: str) -> str:
    """Tolerate a stray ```json fence or prose around the JSON object."""
    text = text.strip()
    if text.startswith("{"):
        return text
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text
