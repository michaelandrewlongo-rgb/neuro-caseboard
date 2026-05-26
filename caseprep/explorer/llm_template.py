"""LLM-powered Explorer template generator.

Calls DeepSeek v4 Flash (via OpenRouter) to generate procedure-family-specific
question cards when no hand-written template exists.  The LLM produces
structured anatomy/operative/risk cards based on its broad clinical knowledge,
which then flow through the normal Enricher→Auditor→Compiler pipeline.

Graceful fallback: returns None when the API key is unavailable, allowing
hand-written templates or generic rules to take over.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from caseprep.explorer.question_manifest import QuestionCard, QuestionManifest

logger = logging.getLogger(__name__)

# ── configuration ────────────────────────────────────────────────────────────

_LLM_MODEL = os.environ.get("CASEPREP_LLM_MODEL", "deepseek/deepseek-chat")
_LLM_API_KEY = (
    os.environ.get("OPENROUTER_API_KEY")
    or os.environ.get("CASEPREP_LLM_KEY")
    or ""
)
_LLM_BASE_URL = "https://openrouter.ai/api/v1"
_LLM_TIMEOUT = 30  # seconds — template generation should be fast


def _llm_available() -> bool:
    return bool(_LLM_API_KEY.strip())


# ── prompt ───────────────────────────────────────────────────────────────────

_TEMPLATE_PROMPT = """You are generating a preoperative case preparation template for a neurosurgeon.
Given a procedure description, produce structured question cards for three sections:
1. Anatomy at Risk — critical structures, variants, no-fly zones
2. Operative Plan — positioning, exposure, critical steps, decision points, stop criteria, closure, monitoring, equipment, attending preferences
3. Risk and Rescue — likely complications, catastrophic complications, mitigation, rescue triggers

Each card must have:
- "target_file": "03-anatomy-at-risk.md", "04-operative-plan.md", or "05-risk-and-rescue.md"
- "section_key": MUST be one of these exact values:
    Anatomy: surgical_corridor, landmarks_in_order, neural_structures, arteries_perforators_veins_sinuses, functional_structures, variants, no_fly_zones
    Operative: positioning, exposure, critical_steps, decision_points, stop_points, closure_reconstruction, monitoring, equipment_adjuncts, attending_preferences_questions
    Risk: likely_complications, catastrophic_complications, mitigation, rescue_triggers
- "question": specific, actionable question (80-200 chars)
- "why_it_matters": intraoperative consequence (40-150 chars)
- "compiler_slot": exact heading from the list above in Title Case

Rules:
- Be procedure-specific. For "carotid endarterectomy", ask about shunt use, patch angioplasty, vagus nerve dissection, cross-clamp tolerance. Do NOT ask generic questions about craniotomy or eloquent cortex.
- Cover ALL subsections listed above. Every section_key must have at least one card.
- Use precise clinical terminology (NASCET criteria, AAO-HNS hearing class, etc.)
- Questions should be VERIFY prompts — things the surgeon confirms, not facts stated as answers.
- Output ONLY valid JSON. No markdown, no explanations.

Output format:
{{
  "procedure_family": "short_snake_case_name",
  "cards": [
    {{
      "target_file": "03-anatomy-at-risk.md",
      "section_key": "surgical_corridor",
      "question": "Confirm...",
      "why_it_matters": "Because...",
      "compiler_slot": "Surgical Corridor"
    }},
    ...
  ]
}}

Procedure: {topic}"""


# ── API call ─────────────────────────────────────────────────────────────────


def _call_llm(prompt: str) -> dict[str, Any] | None:
    """Call the LLM and return parsed JSON, or None on failure."""
    import urllib.request

    payload = json.dumps({
        "model": _LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{_LLM_BASE_URL}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {_LLM_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/caseprep",
            "X-Title": "CasePrep Explorer",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=_LLM_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as exc:
        logger.debug("LLM template generation failed: %s", exc)
        return None


# ── response → QuestionCards ─────────────────────────────────────────────────


def _parse_cards(raw: dict[str, Any]) -> list[QuestionCard]:
    """Convert LLM JSON response into QuestionCard objects."""
    cards: list[QuestionCard] = []
    for item in raw.get("cards", []):
        try:
            cards.append(QuestionCard(
                target_file=str(item.get("target_file", "")),
                section_key=str(item.get("section_key", "")),
                question=str(item.get("question", ""))[:300],
                why_it_matters=str(item.get("why_it_matters", ""))[:200],
                compiler_slot=str(item.get("compiler_slot", "")),
                answerability="needs_patient_fact",
            ))
        except Exception:
            continue
    return cards


# ── public API ───────────────────────────────────────────────────────────────


def build_llm_manifest(
    topic: str,
    *,
    procedure_family_id: str = "",
) -> QuestionManifest | None:
    """Generate a procedure-specific QuestionManifest using an LLM.

    Returns None if the LLM is unavailable (no API key) or the call fails.
    """
    if not _llm_available():
        return None

    prompt = _TEMPLATE_PROMPT.format(topic=topic)
    raw = _call_llm(prompt)
    if raw is None:
        return None

    cards = _parse_cards(raw)
    if not cards:
        return None

    family = raw.get("procedure_family", procedure_family_id or "llm_auto")
    return QuestionManifest(procedure_family=family, cards=cards)
