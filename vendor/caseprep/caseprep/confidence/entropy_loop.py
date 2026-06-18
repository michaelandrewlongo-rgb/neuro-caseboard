
"""Entropy-guided refinement loop for low-confidence slot fills.

Single re-roll pattern — not a full reasoning chain. When a slot fill has
high entropy (low confidence), re-generate with a tighter prompt.
"""

from __future__ import annotations

from typing import Any, Callable

from caseprep.confidence.logprobs import compute_entropy, extract_logprobs

# Threshold constants
ENTROPY_THRESHOLD = 1.5   # above this = low confidence, trigger refinement
MAX_REFINEMENTS = 1       # single re-roll, not a reasoning chain


def should_refine(entropy: float, logprob: float) -> bool:
    """Decide whether to trigger the entropy-guided refinement loop.
    
    Returns True when the slot fill has low confidence and would benefit
    from a re-generation with a more constrained prompt.
    """
    return entropy > ENTROPY_THRESHOLD or logprob < -2.0


def build_refinement_prompt(
    original_prompt: str, 
    slot_name: str, 
    reason: str,
) -> str:
    """Construct a tighter prompt for the re-generation attempt.
    
    The refinement prompt adds constraint: force specificity, and require
    the model to explicitly state 'Insufficient data.' rather than fabricate.
    """
    return (
        f"{original_prompt}\n\n"
        f"Your previous answer for '{slot_name}' had low confidence ({reason}). "
        f"Please provide a more specific answer. If you truly cannot determine this "
        f"from the available information, explicitly state 'Insufficient data.' "
        f"Do NOT fabricate an answer. Answer only what the source text supports."
    )


async def entropy_guided_fill(
    llm_call: Callable,
    prompt: str,
    slot_name: str,
    *,
    max_attempts: int = MAX_REFINEMENTS,
) -> tuple[str, dict[str, Any], int]:
    """Fill a slot with entropy-guided refinement.
    
    Args:
        llm_call: async function that takes (prompt, **kwargs) and returns API response dict
        prompt: the original prompt text
        slot_name: human-readable name of the slot being filled
        max_attempts: maximum refinement attempts (default 1)
    
    Returns:
        (text, logprob_result_dict, attempts_used)
    """
    response = await llm_call(prompt, logprobs=True)
    logprob_result = extract_logprobs(response)
    
    attempts = 1
    for attempt in range(1, max_attempts + 1):
        entropy = compute_entropy(
            logprob_result.get("top_logprobs") or []
        )
        logprobs = logprob_result.get("logprobs") or [0.0]
        avg_logprob = sum(logprobs) / len(logprobs) if logprobs else 0.0
        
        if not should_refine(entropy, avg_logprob):
            break
        
        refined_prompt = build_refinement_prompt(
            prompt, slot_name,
            f"entropy={entropy:.2f}, logprob={avg_logprob:.2f}"
        )
        response = await llm_call(refined_prompt, logprobs=True)
        logprob_result = extract_logprobs(response)
        attempts = attempt + 1
    
    text = response["choices"][0]["message"]["content"]
    return text, logprob_result, min(attempts, max_attempts + 1)
