"""LLM-backed CasePrep intent structurer with deterministic fallback.

The LLM is allowed to classify and plan output shape only. It must not answer
clinical questions; schema validation rejects obvious answer-language leakage.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

import httpx

from caseprep.core import OutputIntentPlan
from caseprep.intent.heuristics import heuristic_intent_plan
from caseprep.intent.schema import validate_intent_payload


@dataclass(frozen=True)
class IntentLLMConfig:
    model: str = os.getenv(
        "CASEPREP_INTENT_MODEL",
        os.getenv("CASEPREP_LLM_MODEL", "google/gemini-2.0-flash-001"),
    )
    api_key: str = os.getenv(
        "CASEPREP_INTENT_KEY",
        os.getenv("CASEPREP_LLM_KEY", os.getenv("OPENROUTER_API_KEY", "")),
    )
    base_url: str = os.getenv("CASEPREP_LLM_BASE", "https://openrouter.ai/api/v1")
    timeout: float = float(os.getenv("CASEPREP_INTENT_TIMEOUT", "30"))
    temperature: float = 0.0
    max_tokens: int = 900
    confidence_threshold: float = 0.5


LLMCall = Callable[[str, IntentLLMConfig], Awaitable[Mapping[str, Any]]]

_SYSTEM_PROMPT = """You classify a user's CasePrep request.
Do NOT answer the clinical question.
Do NOT provide outcomes, rates, recommendations, or medical conclusions.
Return only JSON matching this shape:
{
  "intent_type": "operative_briefing" | "literature_review",
  "subtype": "approach" | "technique" | "anatomy_at_risk" | "complication_avoidance" | "perioperative_setup" | "comparative_outcomes" | "incidence" | "risk_factors" | "prognosis" | "complication_rates" | "general_evidence_summary" | "case_prep",
  "confidence": 0.0-1.0,
  "normalized_query": "lowercase user request",
  "entities": {},
  "template_sections": ["compact labels only"],
  "retrieval_priorities": ["compact labels only"],
  "clarification_needed": false,
  "clarification_question": null,
  "warnings": []
}
Allowed top-level intent_type values are exactly: operative_briefing, literature_review.
Use operative_briefing for operative approach, technique, exposure, anatomy-at-risk, setup, steps, or case prep.
Use literature_review for comparative outcomes, incidence/rates, complication rates, risk factors, prognosis, or evidence summaries.
"""


def intent_structurer_enabled() -> bool:
    return os.getenv("CASEPREP_INTENT_STRUCTURER_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _fallback_with_warning(query: str, warning: str) -> OutputIntentPlan:
    fallback = heuristic_intent_plan(query)
    warnings = list(fallback.warnings)
    if warning not in warnings:
        warnings.append(warning)
    return replace(fallback, warnings=warnings)


def _extract_json_object(text: str) -> Mapping[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    return json.loads(stripped)


async def _call_intent_llm(query: str, config: IntentLLMConfig) -> Mapping[str, Any]:
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "CasePrep Intent Structurer",
    }
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"User request: {query}"},
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=config.timeout) as client:
        response = await client.post(
            f"{config.base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    content = data["choices"][0]["message"]["content"]
    return _extract_json_object(content)


async def structure_intent(
    query: str,
    *,
    config: IntentLLMConfig | None = None,
    llm_call: LLMCall | None = None,
) -> OutputIntentPlan:
    """Return an intent plan, falling back safely whenever LLM routing is unsafe."""
    cfg = config or IntentLLMConfig()
    if not intent_structurer_enabled():
        return heuristic_intent_plan(query)
    if not cfg.api_key.strip():
        return _fallback_with_warning(query, "intent_llm_unavailable")

    call = llm_call or _call_intent_llm
    try:
        raw = await call(query, cfg)
    except Exception:
        return _fallback_with_warning(query, "intent_llm_call_failed")

    try:
        plan = validate_intent_payload(raw, source="llm")
    except Exception:
        return _fallback_with_warning(query, "intent_llm_validation_failed")

    if plan.confidence < cfg.confidence_threshold:
        return _fallback_with_warning(query, "intent_llm_low_confidence")

    if not plan.normalized_query:
        plan = replace(plan, normalized_query=" ".join((query or "").strip().lower().split()))
    if plan.source != "llm":
        plan = replace(plan, source="llm")
    return plan
