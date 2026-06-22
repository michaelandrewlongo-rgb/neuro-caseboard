"""LLM-backed Explorer — clinical depth via PLANNER -> AUTHOR -> CRITIC.

A single dense prompt caps depth: the model emits one generic card per slot and the
case-defining items flicker in and out run-to-run. This module decomposes generation so
the depth becomes reliable:

  PLANNER (strong model, small call): enumerate the case-defining coverage THEMES, seeded
    by a topic-agnostic archetype->dimensions ontology (guarantees structural dimensions
    like hydrocephalus-if-posterior-fossa). Self-consistency union over a few samples kills
    run-to-run flicker.
  AUTHOR (cheap model, big call): expand each checklist theme into concrete cards; assert,
    do not quiz; hedge rather than invent a specific (a wrong named vessel is worse than a
    general statement).
  CRITIC (strong model, small call): add cards for any still-missing theme, and re-anchor
    any wrong/unverifiable specific DOWN to a correct statement instead of deleting it.

The strong model goes on the small planner/critic calls (where capability is cheap and
high-impact) and the cheap model on the big author call. Every model call is injected
(``*_fn``) so the parse/validate/orchestration logic is testable offline and deterministic.
Any failure degrades gracefully (ontology floor for the plan; draft kept if critic fails).
"""

from __future__ import annotations

import json
import logging
import os
import re

from caseprep.explorer.question_manifest import (
    QuestionCard,
    QuestionManifest,
    _ANATOMY_SLOTS,
    _OPERATIVE_SLOTS,
    _RISK_SLOTS,
)

from neuro_caseboard.ontology import required_dimensions

# section_key -> compiler_slot, and which keys are legal for each section file.
_SLOTS_BY_FILE = {
    "03-anatomy-at-risk.md": _ANATOMY_SLOTS,
    "04-operative-plan.md": _OPERATIVE_SLOTS,
    "05-risk-and-rescue.md": _RISK_SLOTS,
}

_log = logging.getLogger(__name__)

_OPENROUTER_AUTHOR = "openai/gpt-4o"       # cheap, big-token author call
_OPENROUTER_STRONG = "google/gemini-2.5-pro"  # strong, small planner/critic calls
_VERTEX_DEFAULT = "gemini-2.5-pro"         # quality-first on the GCP free credit
_MIN_CARDS = 6  # below this we treat the author generation as failed and fall back

_SECTION_KEYS = """  03-anatomy-at-risk.md: surgical_corridor, landmarks_in_order, neural_structures, \
arteries_perforators_veins_sinuses, functional_structures, variants, no_fly_zones
  04-operative-plan.md: positioning, exposure, critical_steps, decision_points, \
stop_points, closure_reconstruction, monitoring, equipment_adjuncts, attending_preferences_questions
  05-risk-and-rescue.md: likely_complications, catastrophic_complications, mitigation, rescue_triggers"""


def _llm_provider() -> str:
    """The active LLM provider. An explicit ``CASEBOARD_LLM_PROVIDER``
    (vertex|openrouter) wins; otherwise infer from configured keys. ``vertex`` is opt-in
    (explicit only) so it never activates unexpectedly in tests."""
    p = (os.environ.get("CASEBOARD_LLM_PROVIDER") or "").strip().lower()
    if p:
        return p
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    return ""


def _resolve_model(model: str | None, *, provider: str | None = None) -> str:
    if model:
        return model
    env = os.environ.get("CASEBOARD_LLM_MODEL")
    if env:
        return env
    provider = provider or _llm_provider()
    if provider == "openrouter":
        return _OPENROUTER_AUTHOR
    return _VERTEX_DEFAULT


def _model_for(role: str) -> str:
    """Resolve the model for a pipeline role (author/planner/critic), env-overridable.
    On Vertex the strong model drives EVERY role — with the GCP free credit there is no
    reason to drop the author to a cheap tier (quality over value)."""
    env = {"author": "CASEBOARD_AUTHOR_MODEL", "planner": "CASEBOARD_PLANNER_MODEL",
           "critic": "CASEBOARD_CRITIC_MODEL"}[role]
    m = os.environ.get(env) or os.environ.get("CASEBOARD_LLM_MODEL")
    if m:
        return m
    provider = _llm_provider()
    if provider == "openrouter":
        return _OPENROUTER_AUTHOR if role == "author" else _OPENROUTER_STRONG
    return _VERTEX_DEFAULT


# --- prompts ---------------------------------------------------------------

_PLAN_SYSTEM = """You are a fellowship-trained attending neurosurgeon planning a \
pre-operative case board for ONE specific procedure. Output the case-defining THEMES the \
board must cover across the three sections (Anatomy at Risk, Operative Plan, Risk & \
Rescue), as short noun-phrase labels — NOT prose, NOT questions, NOT cards.

You are given REQUIRED DIMENSIONS; include every one, made specific to THIS exact \
operation, and ADD any other case-defining theme an attending would insist on (named \
structures, perforators/feeders, intra-operative adjuncts, drugs, numeric thresholds, the \
specific catastrophic complications and their rescues). Every theme must be genuinely \
specific to THIS procedure and approach; do NOT include themes from a different operation \
or subspecialty.

Output ONLY JSON: {"themes": ["...", "..."]} with 14-26 concise themes."""

_AUTHOR_SYSTEM = """You are a fellowship-trained attending neurosurgeon writing a \
pre-operative case board for a resident for ONE specific procedure. You are given a \
COVERAGE CHECKLIST of themes; emit AT LEAST ONE concrete card for EVERY checklist theme, \
plus any other case-defining card. Produce 26-40 cards across exactly three sections.

Sections and their section_keys:
- Anatomy at Risk (03-anatomy-at-risk.md): surgical corridor, landmarks in order, neural \
structures, arteries/perforators/veins/sinuses, functional structures, variants, no-fly zones
- Operative Plan (04-operative-plan.md): positioning, exposure, critical steps, decision \
points, stop criteria, closure/reconstruction, monitoring, equipment/adjuncts, attending preferences
- Risk and Rescue (05-risk-and-rescue.md): likely complications, catastrophic \
complications, mitigation, rescue triggers

HOW TO WRITE A CARD (the `question` field):
- Write a DECLARATIVE assertion the surgeon will confirm — STATE the fact, do not ask a \
quiz question. Good: "Recurrent laryngeal nerve runs in the tracheoesophageal groove; the \
right course is more variable." Bad: "What is the course of the recurrent laryngeal \
nerve?" Reserve the interrogative form ONLY for genuinely patient-specific unknowns.
- Each card MUST carry one CONCRETE specific: a named structure AND where it runs/what it \
is adherent to, OR a named device/adjunct (neuronavigation, facial-nerve EMG, ABR, ICG \
videoangiography, micro-Doppler, EVD, ultrasonic aspirator), OR a named drug and its role \
(mannitol, adenosine, nimodipine, dexamethasone, tranexamic acid), OR a numeric threshold, \
OR a named operative maneuver/step sequence.
- DO NOT INVENT. If you are not confident a specific named fact (a vessel's origin, a \
threshold, a relationship) is correct for THIS operation, state the relationship only at \
the level you are sure of, or write that card as an explicit verification question — a \
wrong named specific is worse than a general statement.
- BAN generic filler ("monitor for complications", "confirm attending preference", "stop \
if uncontrollable bleeding", bare "positioning"/"anatomical variants") unless made \
concretely specific to THIS procedure.

RISK AND RESCUE is the DEEPEST section: enumerate the DISTINCT complications THIS operation \
is known for (>=6), and give EACH catastrophic complication its OWN card paired with a \
concrete, named, step-by-step rescue sequence (e.g. expanding cervical wound hematoma \
after ACDF: "open the wound at bedside, evacuate the clot, secure the airway / reintubate, \
return to OR" — NOT "stop and assess").

POST-OPERATIVE PLANNING the attending must decide pre-operatively (CSF diversion / shunt \
plan for hydrocephalus; oncologic staging such as post-op MRI within 48h, full-neuraxis \
MRI, and CSF cytology; adjuvant / tumor-board pathway) is REQUIRED when relevant — place \
these cards under Operative Plan (decision_points or attending_preferences_questions) or \
Risk and Rescue (mitigation). Do not omit them just because there is no post-op section.

HARD RULE: do NOT include content from a different operation or subspecialty.

Output ONLY JSON {"cards":[{"target_file":"...","section_key":"...","question":"...","why_it_matters":"..."}]}
where section_key is one of the exact keys for that target_file:
""" + _SECTION_KEYS

_CRITIC_SYSTEM = """You are the attending reviewing a resident's DRAFT pre-operative case \
board for ONE specific procedure, against a REQUIRED COVERAGE checklist. Do TWO things:

1. ADD concise cards for any checklist theme not yet CONCRETELY covered by the draft, and \
for any other case-defining item an attending would insist on (named feeders/perforators, \
intra-operative adjuncts, drugs and their role, numeric thresholds, named step-by-step \
rescues for each catastrophic complication, AND pre-operatively-planned post-op management \
such as CSF-diversion/shunt plans for hydrocephalus and oncologic staging — place those \
under Operative Plan decision_points/attending_preferences_questions or Risk mitigation). \
Stay strictly on THIS operation.

2. CORRECT any draft card that states a specific anatomical or numeric fact that is WRONG \
or unverifiable for THIS procedure. Re-anchor the claim DOWN to the statement that is \
correct — do NOT delete the card and do NOT invent a new specific. (Example: "the anterior \
choroidal artery arises at the MCA bifurcation" -> "the anterior choroidal artery arises \
from the supraclinoid ICA; know its origin relative to your exposure".)

Write every added card's `question` as a DECLARATIVE assertion that STATES the fact or the \
named step sequence (e.g. "Intra-op rupture: temporary clip on proximal M1, sucker-\
decompress the dome, apply the definitive clip, then confirm M1/M2 patency with ICG") — \
NOT a quiz question ("What is the rescue for rupture?"). Put the substance in `question`, \
not only in `why_it_matters`.

Output ONLY JSON:
{"add": [ {"target_file":"...","section_key":"...","question":"...","why_it_matters":"..."} ],
 "fix": [ {"match":"<unique substring of the draft question to correct>","question":"<corrected assertion>","why_it_matters":"<corrected>"} ]}
Cards in "add" use the exact section_keys:
""" + _SECTION_KEYS


# --- provider calls --------------------------------------------------------

def llm_available() -> bool:
    """True when the active provider is configured and its client lib is importable."""
    provider = _llm_provider()
    if provider == "vertex":
        if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
            return False
        try:
            import google.genai  # noqa: F401
            return True
        except Exception:
            return False
    if provider == "openrouter":
        try:
            import requests  # noqa: F401
            return True
        except Exception:
            return False
    return False


def _openrouter_complete(system: str, user: str, *, model: str | None = None,
                         temperature: float = 0.3, retries: int = 2) -> str:
    """OpenAI-compatible chat completion via OpenRouter. Retries transient failures."""
    import time
    import requests
    payload = {
        "model": _resolve_model(model, provider="openrouter"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": temperature,
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
                headers=headers, json=payload, timeout=240)
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


def _vertex_complete(system: str, user: str, *, model: str | None = None,
                     temperature: float = 0.3) -> str:
    """Vertex AI Gemini completion returning JSON text. Auth via Application Default
    Credentials (``gcloud auth application-default login``); spends the GCP project's
    credit rather than a paid OpenRouter key. Targets google-genai >= 1.0.
    Not unit-tested (network); the dispatch into it is."""
    from google import genai
    from google.genai import types
    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1")
    resp = client.models.generate_content(
        model=_resolve_model(model, provider="vertex"),
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=user)])],
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=32000,
            response_mime_type="application/json"),
    )
    return resp.text or ""


def _default_complete(system: str, user: str, *, model: str | None = None,
                      temperature: float = 0.3) -> str:
    provider = _llm_provider()
    if provider == "vertex":
        return _vertex_complete(system, user, model=model, temperature=temperature)
    if provider == "openrouter":
        return _openrouter_complete(system, user, model=model, temperature=temperature)
    raise RuntimeError(
        "no LLM provider configured: set CASEBOARD_LLM_PROVIDER=vertex "
        "(with GOOGLE_CLOUD_PROJECT + ADC) or OPENROUTER_API_KEY")


# --- parsing / merge helpers ----------------------------------------------

def _extract_json(text: str) -> str:
    """Tolerate a stray ```json fence or prose around the JSON object."""
    text = text.strip()
    if text.startswith("{"):
        return text
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text


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


def _draft_digest(cards) -> str:
    by_file: dict[str, list[str]] = {}
    for c in cards:
        by_file.setdefault(c.target_file, []).append(f"- [{c.section_key}] {c.question}")
    return "\n".join(f"{tf}:\n" + "\n".join(lines) for tf, lines in by_file.items())


def _merge_distinct(base, extra, threshold: float = 0.7):
    """Append *extra* cards that are not near-duplicates (word-overlap > threshold) of any
    card already kept — regardless of slot, so a second distinct card can land in a slot
    the draft already touched (e.g. another catastrophic complication)."""
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


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# --- pipeline roles --------------------------------------------------------

def _plan_enabled() -> bool:
    return os.environ.get("CASEBOARD_LLM_PLAN", "1") != "0"


def _plan_samples() -> int:
    try:
        return max(1, int(os.environ.get("CASEBOARD_PLAN_SAMPLES", "2")))
    except ValueError:
        return 2


def _critic_enabled() -> bool:
    return (os.environ.get("CASEBOARD_LLM_CRITIC", "1") != "0"
            and os.environ.get("CASEBOARD_LLM_REFINE", "1") != "0")


def plan_coverage(topic: str, plan_fn) -> list[str]:
    """Coverage checklist for *topic*: the ontology dimension floor (always, no API),
    unioned with self-consistency samples from the LLM planner (when enabled)."""
    themes = required_dimensions(topic)            # deterministic floor — guarantees structure
    if not _plan_enabled():
        return themes
    seen = {_norm(t) for t in themes}
    user = (f"Procedure: {topic.strip()}\n\nREQUIRED DIMENSIONS (include and make "
            f"specific to this operation):\n" + "\n".join(f"- {d}" for d in themes))
    for _ in range(_plan_samples()):
        try:
            raw = json.loads(_extract_json(plan_fn(_PLAN_SYSTEM, user)))
        except Exception:
            continue
        for t in raw.get("themes", []):
            t = str(t).strip()
            if t and _norm(t) not in seen:
                seen.add(_norm(t))
                themes.append(t)
    return themes


def author_cards(topic: str, themes: list[str], author_fn):
    """Expand the coverage checklist into concrete cards, or None on failure."""
    checklist = "\n".join(f"- {t}" for t in themes)
    user = (f"Procedure: {topic.strip()}\n\nCOVERAGE CHECKLIST (emit >=1 concrete card "
            f"for EACH theme):\n{checklist}")
    try:
        raw = json.loads(_extract_json(author_fn(_AUTHOR_SYSTEM, user)))
    except Exception as exc:
        _log.warning("author stage could not parse model output (%s); the LLM Explorer "
                     "will fall back to the deterministic lane.", type(exc).__name__)
        return None
    raw_count = len(raw.get("cards", []) or [])
    cards = _coerce_cards(raw)
    dropped = raw_count - len(cards)
    if raw_count and dropped:
        # A high drop rate after a successful call is the schema/vocabulary-drift signature
        # (cards rejected by _coerce_cards), distinct from a model outage. PHI-safe: counts
        # only — never card text. No control-flow change: we still return `cards`.
        level = logging.WARNING if (len(cards) < _MIN_CARDS <= raw_count) else logging.DEBUG
        _log.log(level, "author stage: %d/%d cards rejected by schema coercion "
                 "(kept %d, min %d).", dropped, raw_count, len(cards), _MIN_CARDS)
    return cards


def _apply_fixes(cards, fixes):
    """Re-anchor cards the critic flagged: replace the first card whose question contains
    the `match` substring with the corrected assertion (never delete)."""
    out = list(cards)
    for fx in fixes or []:
        try:
            match = str(fx.get("match", "")).strip().lower()
            newq = str(fx.get("question", "")).strip()
        except Exception:
            continue
        if not match or not newq:
            continue
        for i, c in enumerate(out):
            if match in c.question.lower():
                out[i] = QuestionCard(
                    target_file=c.target_file, section_key=c.section_key,
                    question=newq,
                    why_it_matters=(str(fx.get("why_it_matters", "")).strip() or c.why_it_matters),
                    compiler_slot=c.compiler_slot, answerability=c.answerability)
                break
    return out


def critique_cards(topic: str, themes: list[str], cards, critic_fn):
    """Add missing-theme cards and re-anchor fabrications. Best-effort: draft kept on error."""
    user = (f"Procedure: {topic.strip()}\n\nREQUIRED COVERAGE:\n"
            + "\n".join(f"- {t}" for t in themes)
            + f"\n\nDRAFT CARDS:\n{_draft_digest(cards)}")
    try:
        raw = json.loads(_extract_json(critic_fn(_CRITIC_SYSTEM, user)))
    except Exception:
        return cards
    cards = _merge_distinct(cards, _coerce_cards({"cards": raw.get("add", [])}))
    return _apply_fixes(cards, raw.get("fix", []))


def build_llm_manifest(topic: str, *, complete_fn=None, plan_fn=None, author_fn=None,
                       critic_fn=None, model: str | None = None):
    """Generate a case-specific QuestionManifest for *topic* via planner->author->critic,
    or None if the author stage fails / underproduces.

    ``complete_fn`` (if given) drives every role — used by offline tests. Otherwise each
    role binds to its own model (strong planner/critic, cheap author), env-overridable via
    CASEBOARD_{PLANNER,AUTHOR,CRITIC}_MODEL. Planner self-consistency is CASEBOARD_PLAN_SAMPLES;
    set CASEBOARD_LLM_PLAN=0 / CASEBOARD_LLM_CRITIC=0 to disable a stage."""
    if complete_fn is not None:
        plan_fn = plan_fn or complete_fn
        author_fn = author_fn or complete_fn
        critic_fn = critic_fn or complete_fn
    else:
        author_fn = author_fn or (lambda s, u: _default_complete(
            s, u, model=model or _model_for("author"), temperature=0.3))
        plan_fn = plan_fn or (lambda s, u: _default_complete(
            s, u, model=_model_for("planner"), temperature=0.6))
        critic_fn = critic_fn or (lambda s, u: _default_complete(
            s, u, model=_model_for("critic"), temperature=0.2))

    themes = plan_coverage(topic, plan_fn)
    cards = author_cards(topic, themes, author_fn)
    if not cards or len(cards) < _MIN_CARDS:
        return None
    if _critic_enabled():
        cards = critique_cards(topic, themes, cards, critic_fn)
    return QuestionManifest(procedure_family="llm_generated", cards=cards)
