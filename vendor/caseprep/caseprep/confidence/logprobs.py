"""Logprob extraction from LLM API responses."""

from __future__ import annotations

import math
from typing import Any


def extract_logprobs(response_json: dict[str, Any]) -> dict[str, Any]:
    """Parse logprobs from an OpenAI-compatible chat completion response.
    
    Returns dict with keys: tokens (list[str]), logprobs (list[float]), 
    top_logprobs (list[dict]).
    """
    try:
        choice = response_json["choices"][0]
        logprob_data = choice.get("logprobs") or {}
        content = logprob_data.get("content") or []
        return {
            "tokens": [t.get("token", "") for t in content],
            "logprobs": [t.get("logprob", 0.0) for t in content],
            "top_logprobs": [
                {item["token"]: item["logprob"] for item in (t.get("top_logprobs") or [])}
                for t in content
            ],
        }
    except (KeyError, IndexError, TypeError) as e:
        return {"tokens": [], "logprobs": [], "top_logprobs": []}


def compute_entropy(top_logprobs: list[dict[str, float]]) -> float:
    """Shannon entropy over top_logprobs distributions. Lower = more confident.
    
    Args:
        top_logprobs: List of {token: logprob} dicts, one per position.
    
    Returns:
        Shannon entropy in nats. 0.0 for empty input or degenerate distributions.
    """
    if not top_logprobs:
        return 0.0
    # Take the first position's distribution (the key classification token)
    first_dist = top_logprobs[0] if top_logprobs else {}
    if not first_dist:
        return 0.0
    # Convert logprobs to probabilities
    total = 0.0
    probs = []
    for logp in first_dist.values():
        p = math.exp(logp)
        probs.append(p)
        total += p
    if total == 0.0:
        return 0.0
    # Normalize and compute entropy
    entropy = 0.0
    for p in probs:
        if p > 0:
            normalized = p / total
            entropy -= normalized * math.log(normalized)
    return entropy


def content_token_logprobs(
    result: dict[str, Any],
    stop_tokens: set[str] | None = None,
) -> tuple[list[float], int]:
    """Extract logprobs for content-bearing tokens, skipping structural fluff.
    
    Returns (filtered_logprobs, count_of_content_tokens).
    """
    skip = stop_tokens or {"\n", " ", "  ", "`", "```", "- ", "* ", "**", "##", ""}
    tokens = result.get("tokens") or []
    logprobs = result.get("logprobs") or []
    vals = [
        lp for t, lp in zip(tokens, logprobs) 
        if t.strip() not in skip and t.strip()
    ]
    return vals, len(vals)
