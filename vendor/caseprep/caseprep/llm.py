"""LLM client for template synthesis. Uses OpenRouter or any OpenAI-compatible API."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field

import httpx

# Defaults — override via env vars
DEFAULT_MODEL = os.getenv("CASEPREP_LLM_MODEL", "google/gemini-2.0-flash-001")
DEFAULT_API_KEY = os.getenv(
    "CASEPREP_LLM_KEY",
    os.getenv("OPENROUTER_API_KEY", ""),
)
DEFAULT_BASE_URL = os.getenv(
    "CASEPREP_LLM_BASE",
    "https://openrouter.ai/api/v1",
)


@dataclass
class LLMConfig:
    model: str = DEFAULT_MODEL
    api_key: str = DEFAULT_API_KEY
    base_url: str = DEFAULT_BASE_URL
    max_tokens: int = 2000
    temperature: float = 0.3  # low temp for factual synthesis
    timeout: float = 60.0
    max_retries: int = 3


SYNTHESIS_SYSTEM_PROMPT = """\
You are writing a concise case preparation document for a practicing neurosurgeon. Your reader already knows the anatomy and techniques — they need the reasoning, tradeoffs, and evidence that inform decisions.

GUIDELINES:
1. Focus on clinical logic: WHY one approach over another, WHAT the evidence says about outcomes, HOW complications inform technique selection. Do not describe what the reader already knows.
2. Use citations [S1], [S2] to ground specific claims. Weave them naturally into the reasoning.
3. If sources provide numbers or rates, explain what they mean for decision-making, not just what they are.
4. If sources conflict, present the tension rather than picking a side.
5. If insufficient information exists for a section, write "Insufficient data in search results."
6. Use the format that serves the section: checklists for preparation tasks, short tables for tradeoffs or rescue triggers, and compact prose for evidence interpretation. Avoid filler.
7. Be specific. "Endovascular coiling" is vague; "stent-assisted coiling with the jailing technique using a Neuroform Atlas" is useful.

CRITICAL: NUMBER INTEGRITY
- NEVER fabricate, estimate, or infer statistics, percentages, sample sizes, or rates.
- Only use a number if it appears VERBATIM in a source sentence [S1], [S2], etc.
- If you cannot find a specific number in the sources, write "Insufficient data" rather than guessing.
- When quoting a number, cite the exact source sentence that contains it.
- Do not perform arithmetic on source numbers (e.g., do not compute percentages from raw counts unless the source explicitly states the result)."""


def _build_synthesis_user_prompt(
    template_sections: list[tuple[str, str]],
    source_sentences: list[str],
    topic: str,
) -> str:
    """Build the user prompt for section synthesis."""
    sources_block = "\n".join(
        f"[S{i+1}] {s}" for i, s in enumerate(source_sentences)
    )
    sections_block = "\n\n".join(
        f"## {name}\n{placeholder}" for name, placeholder in template_sections
    )
    return f"""\
Topic: {topic}

SOURCE SENTENCES (use these as evidence):
{sources_block}

TEMPLATE TO FILL:
{sections_block}

For each section above, write surgeon-facing case-prep content using checklists, short tables, or compact prose as appropriate. Prefer structured bullets for operative setup, imaging review, complications, rescue triggers, and postop plans. Weave citations [S1], [S2] into factual claims. Mark unsupported fields as `needs input` rather than inventing missing patient-specific details.

CITATION RULES:
- Every factual claim must cite at least one source [S#].
- If a claim draws on multiple sources, cite ALL of them: [S4, S18].
- A number (percentage, rate, n=) MUST appear in the cited source VERBATIM.
- Never combine numbers from different sources into one claim unless you cite all sources.
- If you cannot find a number in any source, do NOT invent one - write `needs input`.
"""


async def _synthesize_call(
    template_sections: list[tuple[str, str]],
    source_sentences: list[str],
    topic: str,
    config: LLMConfig,
) -> str:
    """Single API call to the LLM. Separated for retry logic."""
    user_prompt = _build_synthesis_user_prompt(
        template_sections=template_sections,
        source_sentences=source_sentences,
        topic=topic,
    )

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
    }

    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
    }

    async with httpx.AsyncClient(timeout=config.timeout) as client:
        resp = await client.post(
            f"{config.base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def synthesize_section(
    template_sections: list[tuple[str, str]],  # [(section_name, placeholder), ...]
    source_sentences: list[str],
    topic: str,
    config: LLMConfig | None = None,
) -> str:
    """Send source sentences to LLM, get back synthesized prose for each section.

    Retries up to config.max_retries with exponential backoff on failure.

    Args:
        template_sections: List of (section_header, placeholder_text) pairs
        source_sentences: Numbered source sentences from abstracts
        topic: The case topic
        config: LLM configuration (uses defaults if None)

    Returns:
        Synthesized markdown text, or raises on failure.
    """
    cfg = config or LLMConfig()
    if not cfg.api_key:
        raise RuntimeError("No API key configured. Set CASEPREP_LLM_KEY or OPENROUTER_API_KEY.")

    last_error = None
    for attempt in range(cfg.max_retries):
        try:
            result = await _synthesize_call(template_sections, source_sentences, topic, cfg)
            if not result or not result.strip():
                raise ValueError("empty response from LLM")
            return result
        except (httpx.TimeoutException, httpx.HTTPStatusError, ValueError) as e:
            last_error = e
            if attempt < cfg.max_retries - 1:
                delay = 2 ** attempt  # 1s, 2s, 4s
                print(f"  [retry] LLM call failed (attempt {attempt+1}/{cfg.max_retries}): {e}. "
                      f"Retrying in {delay}s...", file=sys.stderr)
                await asyncio.sleep(delay)

    raise last_error  # type: ignore[misc]


async def synthesize_complications_split(
    source_sentences: list[str],
    topic: str,
    config: LLMConfig | None = None,
    template_sections: list[tuple[str, str]] | None = None,
) -> str:
    """Synthesize complications in two smaller calls to avoid token truncation.

    Splits the template sections in half. Falls back to single call if
    either half fails.
    """
    cfg = config or LLMConfig()

    # Use provided sections or default
    sections = template_sections or [
        ("Intraoperative", "(vascular injury, neurological deficit, etc.)"),
        ("Postoperative", "(CSF leak, infection, hematoma, etc.)"),
        ("Long-Term", "(recurrence, radiation effects, etc.)"),
        ("Risk Mitigation", "(prevention strategies for each category)"),
    ]

    # Split in half
    mid = len(sections) // 2
    part1_sections = sections[:mid] if mid > 0 else sections[:1]
    part2_sections = sections[mid:]

    try:
        part1 = await synthesize_section(
            template_sections=part1_sections,
            source_sentences=source_sentences,
            topic=topic,
            config=cfg,
        )
    except Exception as e:
        print(f"  [complications] Part 1 failed: {e}. Falling back to single call.", file=sys.stderr)
        return await synthesize_section(sections, source_sentences, topic, cfg)

    try:
        part2 = await synthesize_section(
            template_sections=part2_sections,
            source_sentences=source_sentences,
            topic=topic,
            config=cfg,
        )
    except Exception as e:
        print(f"  [complications] Part 2 failed: {e}. Returning Part 1 only.", file=sys.stderr)
        return part1

    return part1.rstrip() + "\n\n" + part2.lstrip()


# ── Guardrail: citation-aware Jaccard + numeric fidelity ─────────────────

def _tokenize(text: str) -> set[str]:
    """Simple word tokenizer for Jaccard similarity."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if len(t) > 2}


def _jaccard(a: str, b: str) -> float:
    """Jaccard similarity between two strings (0.0 to 1.0)."""
    set_a = _tokenize(a)
    set_b = _tokenize(b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _parse_citations(text: str) -> list[int]:
    """Extract [S#] citation numbers from text. Returns list of ints.

    Handles: [S1], [S2], [S1, S2], [S1,S2,S3]
    """
    citations = []
    # Match [S#] or [S#, S#, ...] patterns
    for match in re.finditer(r"\[S\d+(?:,\s*S\d+)*\]", text):
        bracket = match.group(0)
        nums = re.findall(r"S(\d+)", bracket)
        citations.extend(int(n) for n in nums)
    return citations


def _strip_citation(text: str) -> str:
    """Remove [S1], [S2] citation markers from text for comparison."""
    return re.sub(r"\[S\d+(?:,\s*S\d+)*\]", "", text).strip()


def _extract_numbers(text: str) -> set[str]:
    """Extract numeric values (percentages, n= values, rates) from text.

    Returns a set of normalized number strings for exact-matching.
    Examples: "8%" → "8%", "n=234" → "n=234", "5.2%" → "5.2%"
    """
    numbers = set()

    # Percentages: integer or decimal followed by %
    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*%", text):
        numbers.add(f"{m.group(1)}%")

    # n= patterns: n=234, n = 234, N=234
    for m in re.finditer(r"[nN]\s*=\s*(\d+(?:,\d{3})*)", text):
        num = m.group(1).replace(",", "")
        numbers.add(f"n={num}")

    # Standalone rates expressed as "X per Y"
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*per\s*(\d+)", text.lower()):
        numbers.add(f"{m.group(1)} per {m.group(2)}")

    # Mortality/morbidity/common rates: "X% rate" already caught above
    # Additional: odds ratios, hazard ratios
    for m in re.finditer(r"(OR|HR|RR)\s*[:=]?\s*(\d+(?:\.\d+)?)", text):
        numbers.add(f"{m.group(1)} {m.group(2)}")

    return numbers


def _check_numeric_fidelity(claim: str, source_sentence: str) -> tuple[bool, list[str]]:
    """Verify that all numbers in the claim appear verbatim in the source.

    Returns (passed, list_of_missing_numbers).
    """
    claim_nums = _extract_numbers(claim)
    source_text = source_sentence.lower()
    missing = []

    for num in claim_nums:
        # Normalize: strip spaces in the number string for matching
        num_clean = num.replace(" ", "").lower()
        src_clean = source_text.replace(" ", "")
        if num_clean not in src_clean and num.lower() not in source_text:
            missing.append(num)

    return (len(missing) == 0, missing)


def _extract_claims(text: str) -> list[str]:
    """Split synthesized text into individual claims.

    Each line that is a bullet point (-, *, •) or numbered (1., 2.) is a claim.
    Lines shorter than 20 chars or starting with # are skipped.
    "Insufficient data" lines are not claims.

    Fallback: if no bullet/list lines found, treat every non-header line >= 20 chars
    as a claim (prevents the 0/0 edge case when LLM uses paragraph format).
    """
    claims = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "insufficient data" in stripped.lower():
            continue
        if len(stripped) < 20:
            continue
        if stripped[0] in "-*•" or (stripped[0].isdigit() and ". " in stripped[:4]):
            claims.append(stripped)

    # Fallback: if no bullet/structured format detected, treat substantive lines as claims
    if not claims:
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "insufficient data" in stripped.lower():
                continue
            if len(stripped) >= 20:
                claims.append(stripped)

    return claims


@dataclass
class GuardrailResult:
    passed: bool
    claims: list[dict] = field(default_factory=list)
    # Each dict: {"claim": str, "cited_source": str|None, "matched_source": str,
    #              "citation_matched": bool, "score": float, "numeric_fidelity": bool,
    #              "missing_numbers": list[str], "passed": bool}

    @property
    def flagged_count(self) -> int:
        return sum(1 for c in self.claims if not c["passed"])

    @property
    def total_count(self) -> int:
        return len(self.claims)


def verify_synthesis(
    synthesized_text: str,
    source_sentences: list[str],
    threshold: float = 0.20,
    max_flagged_ratio: float = 0.40,
) -> GuardrailResult:
    """Verify synthesized claims against their CITED source sentences.

    For each claim:
    1. Parse [S#] citation(s) from the claim text
    2. Verify Jaccard similarity against the CITED source sentence(s)
    3. Check numeric fidelity: numbers in claim must appear in cited source
    4. If no citation present, fall back to best-match across all sources

    A claim passes only if BOTH Jaccard >= threshold AND numeric fidelity check passes.

    Args:
        synthesized_text: LLM output to verify
        source_sentences: Original source sentences from abstracts (1-indexed in prompt)
        threshold: Minimum Jaccard similarity to consider a claim supported
        max_flagged_ratio: If more than this fraction of claims are unsupported,
                          the entire synthesis is rejected (result.passed = False)

    Returns:
        GuardrailResult with per-claim details and overall pass/fail.
    """
    claims = _extract_claims(synthesized_text)
    if not claims:
        return GuardrailResult(passed=False, claims=[])

    result = GuardrailResult(passed=True, claims=[])

    for claim in claims:
        claim_clean = _strip_citation(claim)
        citations = _parse_citations(claim)

        # Try citation-specific verification first
        citation_matched = False
        best_score = 0.0
        matched_source = ""
        best_cited_source = None
        numeric_ok = True
        missing_numbers: list[str] = []

        if citations:
            for s_idx in citations:
                # Source indices are 1-based in the prompt
                if 1 <= s_idx <= len(source_sentences):
                    cited = source_sentences[s_idx - 1]
                    score = _jaccard(claim_clean, cited)
                    if score > best_score:
                        best_score = score
                        matched_source = cited
                        citation_matched = True
                        best_cited_source = cited
                        # Numeric fidelity against cited source
                        numeric_ok, missing_numbers = _check_numeric_fidelity(claim_clean, cited)

        # Fallback: no citation or citation didn't match — best-match across all
        if not citation_matched:
            for src in source_sentences:
                score = _jaccard(claim_clean, src)
                if score > best_score:
                    best_score = score
                    matched_source = src
            # Numeric fidelity against best-matched source
            if matched_source:
                numeric_ok, missing_numbers = _check_numeric_fidelity(claim_clean, matched_source)

        # A claim passes only if BOTH Jaccard and numeric fidelity pass
        claim_passed = (best_score >= threshold) and numeric_ok

        # Build failure reason for diagnostics
        failure_reasons = []
        if best_score < threshold:
            failure_reasons.append(f"Jaccard {best_score:.2f} < {threshold}")
        if not numeric_ok:
            failure_reasons.append(f"numbers not in source: {missing_numbers}")

        result.claims.append({
            "claim": claim,
            "cited_source": best_cited_source[:200] if best_cited_source else None,
            "matched_source": matched_source[:200] if matched_source else "",
            "citation_matched": citation_matched,
            "score": round(best_score, 3),
            "numeric_fidelity": numeric_ok,
            "missing_numbers": missing_numbers,
            "passed": claim_passed,
            "failure": " | ".join(failure_reasons) if failure_reasons else "",
        })

    # Overall pass/fail: too many unsupported claims
    if result.total_count > 0:
        ratio = result.flagged_count / result.total_count
        if ratio > max_flagged_ratio:
            result.passed = False

    return result
