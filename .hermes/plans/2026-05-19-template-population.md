# Template Population Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Replace blank fill-in-the-blanks templates with synthesized, verified prose. Extract relevant sentences from PubMed abstracts via keyword matching, synthesize them into coherent sections via LLM, then guardrail the output against hallucination by verifying every claim traces back to a source sentence.

**Architecture:** Three-stage pipeline per template:
1. **Extract** — keyword-based sentence extraction from retrieved PubMed abstracts (deterministic, no LLM)
2. **Synthesize** — send extracted sentences to an LLM with strict instructions to produce coherent prose using ONLY the provided source material
3. **Guardrail** — verify each factual claim in the LLM output against source sentences via Jaccard word-overlap similarity; flag unsupported claims; if too many flagged, fall back to raw extracted sentences

**Tech Stack:** Python stdlib (re, difflib) for extraction and guardrails. `httpx` for LLM API calls (already a dependency). OpenRouter API (already configured for Hermes). Model: configurable, defaults to `deepseek/deepseek-chat` (cheap, fast, good at constrained summarization). No new heavy dependencies — no sentence-transformers, no langchain.

**Graceful degradation:** If the LLM call fails (network, API error, rate limit), the pipeline falls back to raw extracted sentences. If guardrails flag >30% of claims as unverifiable, the output is rejected and raw sentences are used instead. This ensures populated templates are always at least as good as the extract-only approach.

**Scope note:** This plan only covers populating the 3 blank templates. It does NOT address radiology image fixes, post-op care search axes, evidence synthesis, or other Tier 2-4 items from the brainstorm.

---

### Current State (what we're changing)

```
_handle_build_caseplan
  │
  ├─ 4 PubMed searches (outcomes, technique, complications, reviews)
  ├─ Collects all_articles, abstracts, structured abstracts
  ├─ Formats everything into one flat markdown 'summary' string
  └─ _write_filled_templates(out_dir, topic, summary)
       ├─ README.md     ← summary + topic (populated!)
       ├─ literature.md ← summary          (populated!)
       ├─ anatomy.md    ← completely blank (FIX THIS)
       ├─ approach.md   ← completely blank (FIX THIS)
       └─ complications.md ← completely blank (FIX THIS)
```

### Target State

```
_handle_build_caseplan
  │
  ├─ 4 PubMed searches (outcomes, technique, complications, reviews)
  ├─ Collects per-axis articles + abstracts into a structured dict
  ├─ Formats markdown summary (unchanged)
  └─ _write_filled_templates(out_dir, topic, summary, axis_data)
       │
       ├─ _populate_anatomy(axis_data)    ├─ _populate_approach(axis_data)    ├─ _populate_complications(axis_data)
       │        │                          │        │                          │        │
       │        ▼                          │        ▼                          │        ▼
       │  1. _extract_relevant_sentences() │  1. _extract_relevant_sentences() │  1. _extract_relevant_sentences()
       │  2. _synthesize_section()   ←LLM  │  2. _synthesize_section()   ←LLM  │  2. _synthesize_section()   ←LLM
       │  3. _guardrail_verify()           │  3. _guardrail_verify()           │  3. _guardrail_verify()
       │        │                          │        │                          │        │
       │   Pass? → write synthesized       │   Pass? → write synthesized       │   Pass? → write synthesized
       │   Fail? → write raw sentences      │   Fail? → write raw sentences      │   Fail? → write raw sentences
       │                                   │                                   │
       ├─ README.md     ← summary + topic (unchanged)
       ├─ literature.md ← summary          (unchanged)
       ├─ anatomy.md    ← synthesized prose (with source citations)
       ├─ approach.md   ← synthesized prose (with source citations)
       └─ complications.md ← synthesized prose (with source citations)
```

---

### Task 1: Refactor per-axis data collection in `_handle_build_caseplan`

**Objective:** Collect per-axis articles with their abstracts into a structured dict instead of letting them go out of scope after each loop iteration.

**Files:**
- Modify: `caseprep/mcp_server.py:785-845`

**Step 1: Add a dict before the search loop**

In `_handle_build_caseplan`, before the `for label, query, filt in searches:` loop, add:
```python
axis_data: dict[str, list[dict]] = {}
```

**Step 2: After each search iteration, store the articles**

Inside the loop, after `all_articles.extend(articles)`, add:
```python
enriched = []
for a in articles:
    entry = dict(a)
    entry["_abstract"] = abstracts.get(a["pmid"], "")
    entry["_structured"] = structured.get(a["pmid"], {})
    enriched.append(entry)
axis_data[label] = enriched
```

**Step 3: Pass axis_data to _write_filled_templates**

Change line 839 from:
```python
_write_filled_templates(out_dir, topic, summary)
```
To:
```python
await _write_filled_templates(out_dir, topic, summary, axis_data)
```

**Step 4: Update _write_filled_templates signature**

Change line 848 from:
```python
def _write_filled_templates(out_dir: Path, topic: str, summary: str) -> None:
```
To:
```python
async def _write_filled_templates(out_dir: Path, topic: str, summary: str, axis_data: dict[str, list[dict]] | None = None) -> None:
```

**Step 5: Run existing tests**

```bash
cd /home/michael/projects/caseprep && python3 -m pytest tests/ -v -k "not test_web and not test_cli"
```
Expected: all generator + radiology tests still pass (axis_data is optional, defaults to None).

---

### Task 2: Create the content extraction function

**Objective:** Given a list of articles (each with `_abstract` and `_structured` fields), scan for sentences matching section-specific keywords and return the best hits.

**Files:**
- Modify: `caseprep/mcp_server.py` (add function after `_write_filled_templates`)

**Step 1: Define keyword sets**

```python
# Keyword groups for targeting abstract sentences to template sections
_ANATOMY_KEYWORDS = [
    "anatomy", "anatomic", "structure", "nerve", "artery", "vein",
    "cistern", "nucleus", "tract", "cortex", "lobe", "fossa",
    "cranial nerve", "cn vii", "cn viii", "brainstem", "cerebell",
    "temporal bone", "sigmoid", "petrous", "cavernous", "sella",
    "foramen", "fissure", "sulcus", "gyrus", "ventricle",
]

_APPROACH_KEYWORDS = [
    "approach", "technique", "positioning", "craniotomy", "incision",
    "resection", "dissection", "exposure", "drilling", "retraction",
    "microsurgical", "endoscopic", "keyhole", "minimally invasive",
    "monitoring", "neuromonitoring", "ssep", "mep", "emg", "baer",
    "intraoperative", "neuronavigation", "stereotactic", "frameless",
    "bone flap", "dura", "closure", "hemostasis",
]

_COMPLICATION_KEYWORDS = [
    "complication", "risk", "mortality", "morbidity", "deficit",
    "cerebrospinal fluid leak", "csf leak", "infection", "meningitis",
    "hematoma", "hemorrhage", "ischemia", "infarction", "edema",
    "seizure", "hydrocephalus", "thromboembolism", "dvt", "pe",
    "facial nerve", "hearing loss", "anosmia", "diplopia",
    "rate", "%", "percent", "incidence", "n=",
]
```

**Step 2: Write the sentence extractor**

```python
def _extract_relevant_sentences(
    articles: list[dict],
    keywords: list[str],
    max_sentences: int = 8,
    max_per_article: int = 2,
) -> list[str]:
    """Scan article abstracts for sentences matching keywords.

    Returns up to max_sentences relevant sentences, sorted by keyword
    match density (descending). Each article contributes at most
    max_per_article sentences to prevent one paper from dominating.
    """
    import re

    hits: list[tuple[int, str]] = []  # (score, sentence)
    seen: set[str] = set()  # deduplicate near-identical sentences

    for article in articles:
        article_hits = 0
        # Combine abstract + structured abstract sections into one text block
        text = article.get("_abstract", "")
        structured = article.get("_structured", {})
        if structured:
            text += " " + " ".join(structured.values())

        # Split into sentences (crude but effective: split on .!? followed by space/capital)
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)

        for sent in sentences:
            if article_hits >= max_per_article:
                break
            sent_clean = sent.strip()
            if len(sent_clean) < 30:  # skip fragments
                continue
            # Deduplicate
            norm = sent_clean.lower()[:60]
            if norm in seen:
                continue

            # Score: count keyword matches in this sentence
            score = 0
            sent_lower = sent_clean.lower()
            for kw in keywords:
                if kw in sent_lower:
                    score += 1

            if score >= 2:  # require at least 2 keyword hits for relevance
                hits.append((score, sent_clean))
                seen.add(norm)
                article_hits += 1

    # Sort by score descending, take top N
    hits.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in hits[:max_sentences]]
```

**Step 3: Run ad-hoc test**

```bash
cd /home/michael/projects/caseprep && python3 -c "
from caseprep.mcp_server import _extract_relevant_sentences
# Fake article with abstract
articles = [{
    '_abstract': 'The retrosigmoid approach provides excellent exposure of the cerebellopontine angle. Facial nerve monitoring reduces complication rates.',
    '_structured': {},
}]
result = _extract_relevant_sentences(articles, ['approach', 'nerve', 'complication'])
assert len(result) == 2
print('OK:', result)
"
```
Expected: prints 2 extracted sentences.

---

### Task 3: Populate anatomy.md using extracted content

**Objective:** Replace the blank anatomy.md with content extracted from the "Surgical Technique" and "Reviews" search axes.

**Files:**
- Modify: `caseprep/mcp_server.py:862-873` (anatomy.md section of `_write_filled_templates`)

**Step 1: Extract anatomy content**

At the top of `_write_filled_templates`, add:
```python
if axis_data:
    technique_articles = axis_data.get("Surgical Technique", [])
    reviews_articles = axis_data.get("Reviews / Landmarks", [])
    anatomy_articles = technique_articles + reviews_articles
    anatomy_sentences = _extract_relevant_sentences(anatomy_articles, _ANATOMY_KEYWORDS)
    approach_sentences = _extract_relevant_sentences(technique_articles, _APPROACH_KEYWORDS)

    outcomes_articles = axis_data.get("Outcomes / Evidence", [])
    complications_articles = axis_data.get("Complications", [])
    complication_sentences = _extract_relevant_sentences(
        outcomes_articles + complications_articles, _COMPLICATION_KEYWORDS, max_sentences=10
    )
else:
    anatomy_sentences = []
    approach_sentences = []
    complication_sentences = []
```

**Step 2: Replace anatomy.md template**

Change lines 862-873 to:
```python
anatomy_lines = [
    f"# Relevant Anatomy — {topic}\n",
    "## Key Structures\n",
]
if anatomy_sentences:
    for s in anatomy_sentences[:4]:
        anatomy_lines.append(f"- {s}\n")
else:
    anatomy_lines.append("- (list relevant structures — no specific anatomy content found in search results)\n")

anatomy_lines.extend([
    "\n## Vascular Supply\n",
    "- (arteries, veins — review full papers above for detail)\n",
    "\n## Adjacent / At-Risk Structures\n",
    "- (nerves, tracts, cisterns — review full papers above for detail)\n",
    "\n## Anatomic Variants\n",
    "- (common variants — review full papers above for detail)\n",
])
(out_dir / "anatomy.md").write_text("".join(anatomy_lines), encoding="utf-8")
```

---

### Task 4: Populate approach.md using extracted content

**Objective:** Replace the blank approach.md with content extracted from the "Surgical Technique" search axis.

**Files:**
- Modify: `caseprep/mcp_server.py:875-891` (approach.md section of `_write_filled_templates`)

**Step 1: Replace approach.md template**

Change lines 875-891 to:
```python
approach_lines = [
    f"# Surgical Approach — {topic}\n",
    "## Approach Selection\n",
    "- **Approach:** (fill in — see literature below for relevant approaches)\n",
    "- **Rationale:** (fill in)\n",
    "\n## Positioning\n",
    "- (supine, prone, lateral, sitting — see literature below)\n",
    "\n## Key Findings from Literature\n",
]
if approach_sentences:
    for i, s in enumerate(approach_sentences[:6], 1):
        approach_lines.append(f"{i}. {s}\n")
else:
    approach_lines.append("- (no specific technique content found in search results)\n")

approach_lines.extend([
    "\n## Intraoperative Monitoring\n",
    "- (SSEP, MEP, EMG, BAER — review full papers above for detail)\n",
    "\n## Pitfalls\n",
    "- (common errors, how to avoid — review full papers above for detail)\n",
])
(out_dir / "approach.md").write_text("".join(approach_lines), encoding="utf-8")
```

---

### Task 5: Populate complications.md using extracted content

**Objective:** Replace the blank complications.md with content extracted from the "Complications" and "Outcomes" search axes.

**Files:**
- Modify: `caseprep/mcp_server.py:899-910` (complications.md section of `_write_filled_templates`)

**Step 1: Replace complications.md template**

Change lines 899-910 to:
```python
complication_lines = [
    f"# Potential Complications — {topic}\n",
    "## Findings from Literature\n",
]
if complication_sentences:
    for i, s in enumerate(complication_sentences[:8], 1):
        complication_lines.append(f"{i}. {s}\n")
else:
    complication_lines.append("- (no specific complication content found in search results)\n")

complication_lines.extend([
    "\n## Risk Mitigation\n",
    "- (prevention strategies — review full papers above for detail)\n",
])
(out_dir / "complications.md").write_text("".join(complication_lines), encoding="utf-8")
```

---

### Task 6: Add LLM configuration and API call helper

**Objective:** Add a configurable LLM client module that calls OpenRouter (or any OpenAI-compatible API) for section synthesis. Uses the configured Hermes provider with a cheap/fast model default.

**Files:**
- Create: `caseprep/llm.py`

**Step 1: Write the LLM module**

```python
"""LLM client for template synthesis. Uses OpenRouter or any OpenAI-compatible API."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import httpx

# Defaults — override via env vars
DEFAULT_MODEL = os.getenv("CASEPREP_LLM_MODEL", "deepseek/deepseek-chat")
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
    max_tokens: int = 800
    temperature: float = 0.3  # low temp for factual synthesis
    timeout: float = 30.0


SYNTHESIS_SYSTEM_PROMPT = """\
You are a neurosurgical editor synthesizing research findings for a case preparation document.

RULES (follow strictly):
1. ONLY use facts explicitly stated in the provided source sentences.
2. Do NOT add any medical knowledge, statistics, or details not present in the source text.
3. If source sentences provide N numbers or percentages, include them verbatim.
4. If insufficient information exists for any section, write "Insufficient data in search results."
5. Output must be in markdown format matching the provided template structure.
6. For every factual claim, cite which source sentence (by number) supports it: [S1], [S2], etc.
7. Keep each bullet point to 1-2 sentences. Be concise.
8. Do NOT use phrases like "the literature suggests" or "studies show" — just state the facts."""


async def synthesize_section(
    template_sections: list[tuple[str, str]],  # [(section_name, placeholder), ...]
    source_sentences: list[str],
    topic: str,
    config: LLMConfig | None = None,
) -> str:
    """Send source sentences to LLM, get back synthesized prose for each section.

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

    # Build user prompt
    sources_block = "\n".join(
        f"[S{i+1}] {s}" for i, s in enumerate(source_sentences)
    )
    sections_block = "\n\n".join(
        f"## {name}\n{placeholder}" for name, placeholder in template_sections
    )

    user_prompt = f"""\
Topic: {topic}

SOURCE SENTENCES (only use facts from these):
{sources_block}

TEMPLATE TO FILL:
{sections_block}

For each section above, replace the placeholder text with facts from the source sentences.
Cite sources using [S1], [S2] notation where each sentence supported a claim.
If no source sentence supports a section, write "Insufficient data in search results."
"""

    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
    }

    payload = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": cfg.max_tokens,
        "temperature": cfg.temperature,
    }

    async with httpx.AsyncClient(timeout=cfg.timeout) as client:
        resp = await client.post(
            f"{cfg.base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
```

**Step 2: Verify the module loads**

```bash
cd /home/michael/projects/caseprep && python3 -c "from caseprep.llm import synthesize_section, LLMConfig; print('OK')"
```
Expected: "OK" (loads without errors).

---

### Task 7: Build the guardrail verifier

**Objective:** After LLM synthesis, verify every claim traces back to at least one source sentence. Use Jaccard word-overlap similarity (no ML deps). Flag unsupported claims. If >30% flagged, reject the output.

**Files:**
- Modify: `caseprep/llm.py` (add guardrail functions)

**Step 1: Add guardrail functions to llm.py**

```python
def _tokenize(text: str) -> set[str]:
    """Simple word tokenizer for Jaccard similarity."""
    import re
    # Lowercase, strip punctuation, split on whitespace, drop short tokens
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if len(t) > 2}


def _jaccard(a: str, b: str) -> float:
    """Jaccard similarity between two strings (0.0 to 1.0)."""
    set_a = _tokenize(a)
    set_b = _tokenize(b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _extract_claims(text: str) -> list[str]:
    """Split synthesized text into individual claims.
    
    Each line that is a bullet point (-, *, •) or numbered (1., 2.) is a claim.
    Lines under section headers are grouped.
    Lines shorter than 20 chars or starting with # are skipped.
    """
    claims = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Skip "Insufficient data" lines — they're not claims
        if "insufficient data" in stripped.lower():
            continue
        if len(stripped) < 20:
            continue
        if stripped[0] in "-*•" or (stripped[0].isdigit() and ". " in stripped[:4]):
            claims.append(stripped)
        # Also catch continuation lines after a bullet
        elif claims and not stripped.startswith("["):
            pass  # continuation, skip for simplicity
    return claims


def _strip_citation(text: str) -> str:
    """Remove [S1], [S2] citation markers from text for comparison."""
    import re
    return re.sub(r"\[S\d+(?:,\s*S\d+)*\]", "", text).strip()


@dataclass
class GuardrailResult:
    passed: bool
    claims: list[dict] = field(default_factory=list)
    # Each dict: {"claim": str, "best_source": str, "score": float, "passed": bool}

    @property
    def flagged_count(self) -> int:
        return sum(1 for c in self.claims if not c["passed"])

    @property
    def total_count(self) -> int:
        return len(self.claims)


def verify_synthesis(
    synthesized_text: str,
    source_sentences: list[str],
    threshold: float = 0.15,
    max_flagged_ratio: float = 0.30,
) -> GuardrailResult:
    """Verify synthesized claims against source sentences.

    Args:
        synthesized_text: LLM output to verify
        source_sentences: Original source sentences from abstracts
        threshold: Minimum Jaccard similarity to consider a claim supported
        max_flagged_ratio: If more than this fraction of claims are unsupported,
                          the entire synthesis is rejected (result.passed = False)

    Returns:
        GuardrailResult with per-claim details and overall pass/fail.
    """
    claims = _extract_claims(synthesized_text)
    if not claims:
        return GuardrailResult(passed=False)

    result = GuardrailResult(passed=True, claims=[])

    for claim in claims:
        claim_clean = _strip_citation(claim)
        best_score = 0.0
        best_source = ""

        for src in source_sentences:
            score = _jaccard(claim_clean, src)
            if score > best_score:
                best_score = score
                best_source = src

        claim_passed = best_score >= threshold
        result.claims.append({
            "claim": claim,
            "best_source": best_source[:200],
            "score": round(best_score, 3),
            "passed": claim_passed,
        })

    # Overall pass/fail: too many unsupported claims
    if result.total_count > 0:
        ratio = result.flagged_count / result.total_count
        if ratio > max_flagged_ratio:
            result.passed = False

    return result
```

**Step 2: Run ad-hoc test**

```bash
cd /home/michael/projects/caseprep && python3 -c "
from caseprep.llm import verify_synthesis, _jaccard, _extract_claims

# Test Jaccard
assert _jaccard('cerebrospinal fluid leak', 'CSF leak occurred') > 0.0
assert _jaccard('apple banana', 'zebra xylophone') == 0.0

# Test claim extraction
text = '## Complications\n- CSF leak rate was 5% [S1]\n- Meningitis in 2% [S3]\n# Header skipped'
claims = _extract_claims(text)
assert len(claims) == 2, f'Expected 2 claims, got {len(claims)}'

# Test verification
sources = ['CSF leak occurred in 8% of patients', 'Meningitis was observed in 2%']
synth = '- CSF leak in 8 percent [S1]\n- Meningitis rate 2% [S2]'
result = verify_synthesis(synth, sources)
assert result.passed, f'Expected pass, got {result.flagged_count} flagged'

# Test hallucination detection
synth_bad = '- Mortality rate was 50% [S1]\n- Avian flu complication [S2]'
result_bad = verify_synthesis(synth_bad, sources)
assert not result_bad.passed or result_bad.flagged_count > 0, 'Should flag hallucinations'

print('All guardrail tests passed')
"
```
Expected: "All guardrail tests passed".

---

### Task 8: Wire synthesis + guardrails into _write_filled_templates

**Objective:** Replace the raw-sentence template population (Tasks 3-5) with the full 3-stage pipeline: extract → synthesize → guardrail → write.

**Files:**
- Modify: `caseprep/mcp_server.py` (refactor `_write_filled_templates`)

**Step 1: Add the per-section populate helper**

Replace the inline template writing in `_write_filled_templates` with calls to a new helper function. Add this function:

```python
def _populate_section(
    articles: list[dict],
    keywords: list[str],
    template_sections: list[tuple[str, str]],
    topic: str,
    section_title: str,
    max_extracted: int = 10,
) -> str:
    """Run extract → synthesize → guardrail pipeline for one template section.

    Returns the final markdown content to write to the file.
    """
    from caseprep.llm import synthesize_section, verify_synthesis

    # Stage 1: Extract
    extracted = _extract_relevant_sentences(articles, keywords, max_sentences=max_extracted)

    if not extracted:
        # No content at all — write graceful fallback
        lines = [f"# {section_title} — {topic}\n"]
        for name, placeholder in template_sections:
            lines.append(f"## {name}\n")
            lines.append(f"{placeholder}\n")
        return "\n".join(lines)

    # Stage 2: Synthesize via LLM (note: called from async context in _write_filled_templates)
    try:
        synthesized = await synthesize_section(
            template_sections=template_sections,
            source_sentences=extracted,
            topic=topic,
        ))
    except Exception as exc:
        # LLM failed — fall back to raw extracted sentences
        lines = [f"# {section_title} — {topic}\n"]
        lines.append("> *LLM synthesis unavailable — showing raw extracted findings.*\n")
        for name, placeholder in template_sections:
            lines.append(f"## {name}\n")
            lines.append(f"- (see source sentences below)\n")
        lines.append("\n## Source Sentences from Literature\n")
        for i, s in enumerate(extracted, 1):
            lines.append(f"{i}. {s}\n")
        return "\n".join(lines)

    # Stage 3: Guardrail
    result = verify_synthesis(synthesized, extracted)
    if result.passed:
        # Add a header + the verified output
        lines = [f"# {section_title} — {topic}\n"]
        lines.append(synthesized)
        if result.flagged_count > 0:
            lines.append(f"\n> *{result.flagged_count}/{result.total_count} claims flagged during verification.*\n")
        else:
            lines.append(f"\n> *All {result.total_count} claims verified against source sentences.*\n")
        return "\n".join(lines)
    else:
        # Too many unsupported claims — fall back to raw sentences
        lines = [f"# {section_title} — {topic}\n"]
        lines.append(f"> *LLM synthesis rejected: {result.flagged_count}/{result.total_count} claims could not be verified. Showing raw source sentences instead.*\n")
        for name, placeholder in template_sections:
            lines.append(f"## {name}\n")
            lines.append(f"- (see source sentences below)\n")
        lines.append("\n## Source Sentences from Literature\n")
        for i, s in enumerate(extracted, 1):
            lines.append(f"{i}. {s}\n")
        return "\n".join(lines)
```

**Step 2: Refactor _write_filled_templates to use _populate_section**

Replace the anatomy, approach, and complications sections of `_write_filled_templates` with calls to `_populate_section`. The function now becomes:

```python
def _write_filled_templates(
    out_dir: Path, topic: str, summary: str,
    axis_data: dict[str, list[dict]] | None = None,
) -> None:
    """Write filled-in markdown templates with LLM-synthesized content."""

    # README.md — unchanged
    (out_dir / "README.md").write_text(
        f"# {topic}\n\n"
        f"## Case Overview\n\n"
        f"- **Topic:** {topic}\n"
        f"- **Date:** (fill in)\n"
        f"- **Presenter:** (fill in)\n\n"
        f"## Literature Summary\n\n"
        f"{summary}\n",
        encoding="utf-8",
    )

    # literature.md — unchanged
    (out_dir / "literature.md").write_text(
        f"# Literature Review — {topic}\n\n{summary}\n",
        encoding="utf-8",
    )

    # If no axis_data (backwards compat), write blank templates
    if not axis_data:
        for name, template in [
            ("anatomy.md", "Relevant Anatomy"),
            ("approach.md", "Surgical Approach"),
            ("complications.md", "Potential Complications"),
        ]:
            (out_dir / name).write_text(
                f"# {template} — {topic}\n\n"
                f"## (no data available)\n\n"
                f"- (run build_caseplan to populate this section)\n",
                encoding="utf-8",
            )
        return

    # Gather articles per section
    technique_articles = axis_data.get("Surgical Technique", [])
    reviews_articles = axis_data.get("Reviews / Landmarks", [])
    outcomes_articles = axis_data.get("Outcomes / Evidence", [])
    complications_articles = axis_data.get("Complications", [])

    # ── anatomy.md ─────────────────────────────────────────────────────
    anatomy_text = await _populate_section(
        articles=technique_articles + reviews_articles,
        keywords=_ANATOMY_KEYWORDS,
        template_sections=[
            ("Key Structures", "(list relevant structures)"),
            ("Vascular Supply", "(arteries, veins)"),
            ("Adjacent / At-Risk Structures", "(nerves, tracts, cisterns)"),
            ("Anatomic Variants", "(common variants to be aware of)"),
        ],
        topic=topic,
        section_title="Relevant Anatomy",
    )
    (out_dir / "anatomy.md").write_text(anatomy_text, encoding="utf-8")

    # ── approach.md ────────────────────────────────────────────────────
    approach_text = await _populate_section(
        articles=technique_articles,
        keywords=_APPROACH_KEYWORDS,
        template_sections=[
            ("Approach Selection", "- **Approach:** (fill in)\n- **Rationale:** (fill in)"),
            ("Positioning", "(supine, prone, lateral, sitting, etc.)"),
            ("Key Steps", "1.\n2.\n3."),
            ("Intraoperative Monitoring", "(SSEP, MEP, EMG, BAER)"),
            ("Pitfalls", "(common errors and how to avoid them)"),
        ],
        topic=topic,
        section_title="Surgical Approach",
    )
    (out_dir / "approach.md").write_text(approach_text, encoding="utf-8")

    # ── complications.md ───────────────────────────────────────────────
    complications_text = await _populate_section(
        articles=complications_articles + outcomes_articles,
        keywords=_COMPLICATION_KEYWORDS,
        template_sections=[
            ("Intraoperative", "(vascular injury, neurological deficit, etc.)"),
            ("Postoperative", "(CSF leak, infection, hematoma, etc.)"),
            ("Long-Term", "(recurrence, radiation effects, etc.)"),
            ("Risk Mitigation", "(prevention strategies for each category)"),
        ],
        topic=topic,
        section_title="Potential Complications",
    )
    (out_dir / "complications.md").write_text(complications_text, encoding="utf-8")
```

**Step 3: Verify async integration**

`_handle_build_caseplan` is already `async def`, so `await _write_filled_templates(...)` works without changes to the call structure. The `_populate_section` helper must be `async def` so it can await `synthesize_section`. No new imports needed — `asyncio` is already imported in mcp_server.py.

**Step 4: Run a quick syntax check**

```bash
cd /home/michael/projects/caseprep && python3 -c "from caseprep.mcp_server import _write_filled_templates, _populate_section; print('Import OK')"
```
Expected: "Import OK".

---

### Task 9: Add tests for content extraction

**Objective:** Verify the `_extract_relevant_sentences` function works correctly with realistic PubMed abstract data.

**Files:**
- Create: `tests/test_template_population.py`

**Step 1: Write the test file**

```python
"""Tests for template population — content extraction from abstracts."""

import pytest
from caseprep.mcp_server import _extract_relevant_sentences, _ANATOMY_KEYWORDS, _APPROACH_KEYWORDS, _COMPLICATION_KEYWORDS


class TestExtractRelevantSentences:
    def test_extracts_anatomy_sentences(self):
        articles = [{
            "_abstract": (
                "The cerebellopontine angle contains the facial nerve and "
                "vestibulocochlear nerve. The anterior inferior cerebellar artery "
                "courses through the cistern. Anatomic variants of the sigmoid "
                "sinus may affect the surgical corridor."
            ),
            "_structured": {},
        }]
        result = _extract_relevant_sentences(articles, _ANATOMY_KEYWORDS)
        assert len(result) > 0
        assert any("nerve" in s.lower() for s in result)

    def test_extracts_approach_sentences(self):
        articles = [{
            "_abstract": (
                "The retrosigmoid approach provides excellent exposure. "
                "Intraoperative neuromonitoring with facial nerve EMG reduces "
                "the risk of postoperative deficit. The craniotomy should expose "
                "the transverse-sigmoid junction."
            ),
            "_structured": {},
        }]
        result = _extract_relevant_sentences(articles, _APPROACH_KEYWORDS)
        assert len(result) >= 2

    def test_extracts_complication_sentences(self):
        articles = [{
            "_abstract": (
                "CSF leak occurred in 8% of patients. The mortality rate was "
                "less than 1%. Meningitis was observed in 2% of cases. "
                "Facial nerve palsy was the most common complication at 12%."
            ),
            "_structured": {},
        }]
        result = _extract_relevant_sentences(articles, _COMPLICATION_KEYWORDS)
        assert len(result) > 0
        assert any("%" in s for s in result)

    def test_empty_articles_returns_empty(self):
        result = _extract_relevant_sentences([], _ANATOMY_KEYWORDS)
        assert result == []

    def test_no_matching_keywords_returns_empty(self):
        articles = [{
            "_abstract": "The weather was sunny with clear skies.",
            "_structured": {},
        }]
        result = _extract_relevant_sentences(articles, _ANATOMY_KEYWORDS)
        assert result == []

    def test_respects_max_sentences(self):
        articles = [{
            "_abstract": (
                "The artery was dissected. The nerve was identified. "
                "The cistern was opened. The cortex was retracted. "
                "The vein was preserved. The tract was avoided."
            ),
            "_structured": {},
        }]
        result = _extract_relevant_sentences(articles, _ANATOMY_KEYWORDS, max_sentences=3)
        assert len(result) <= 3

    def test_uses_structured_abstract(self):
        articles = [{
            "_abstract": "",
            "_structured": {
                "METHODS": "We used a retrosigmoid craniotomy approach with "
                           "facial nerve monitoring and continuous EMG.",
                "RESULTS": "CSF leak rate was 5% and meningitis rate was 1%.",
            },
        }]
        anatomy_result = _extract_relevant_sentences(articles, _ANATOMY_KEYWORDS)
        approach_result = _extract_relevant_sentences(articles, _APPROACH_KEYWORDS)
        complication_result = _extract_relevant_sentences(articles, _COMPLICATION_KEYWORDS)
        # Structured abstract should be searched too
        assert len(approach_result) > 0 or len(complication_result) > 0
```

**Step 2: Run the tests**

```bash
cd /home/michael/projects/caseprep && python3 -m pytest tests/test_template_population.py -v
```
Expected: 7 passed.

---

### Task 10: Add tests for guardrail verifier

**Objective:** Verify the `verify_synthesis` function correctly passes supported claims, flags hallucinations, and respects the max_flagged_ratio threshold.

**Files:**
- Modify: `tests/test_template_population.py` (add guardrail test class)

**Step 1: Add guardrail tests**

```python
class TestGuardrailVerify:
    def test_passes_supported_claims(self):
        from caseprep.llm import verify_synthesis
        sources = [
            "CSF leak occurred in 8% of patients (N=234).",
            "Meningitis rate was 1.5% in the retrosigmoid approach group.",
        ]
        synth = "- CSF leak rate was 8 percent [S1]\n- Meningitis rate 1.5 percent [S2]"
        result = verify_synthesis(synth, sources)
        assert result.passed
        assert result.flagged_count == 0

    def test_flags_hallucinated_claims(self):
        from caseprep.llm import verify_synthesis
        sources = ["The tumor was resected via retrosigmoid approach."]
        synth = "- Mortality rate was 50% [S1]\n- Length of stay averaged 3 days [S1]"
        result = verify_synthesis(synth, sources)
        # At least one claim should be flagged
        assert result.flagged_count > 0

    def test_rejects_when_over_threshold(self):
        from caseprep.llm import verify_synthesis
        sources = ["The approach provides good exposure."]
        synth = "- Mortality was 5% [S1]\n- Infection rate 10% [S1]\n- CSF leak 8% [S1]\n- Seizure 3% [S1]"
        result = verify_synthesis(synth, sources, max_flagged_ratio=0.25)
        assert not result.passed  # 4 claims, all hallucinated > 25%

    def test_handles_insufficient_data_lines(self):
        from caseprep.llm import verify_synthesis, _extract_claims
        # "Insufficient data" lines should not be extracted as claims
        text = "- CSF leak rate was 5% [S1]\n- Insufficient data in search results.\n- Meningitis 2% [S2]"
        claims = _extract_claims(text)
        assert len(claims) == 2  # insufficient data line skipped

    def test_empty_synthesis_fails(self):
        from caseprep.llm import verify_synthesis
        result = verify_synthesis("", ["some source"])
        assert not result.passed
```

**Step 2: Run guardrail tests**

```bash
cd /home/michael/projects/caseprep && python3 -m pytest tests/test_template_population.py::TestGuardrailVerify -v
```
Expected: 5 passed.

---

### Task 11: Integration test — run build_caseplan and verify populated files

**Objective:** Run a real `build_caseplan` and check that anatomy.md, approach.md, and complications.md contain extracted content (not blank).

**Files:**
- Modify: `tests/test_template_population.py` (add integration test)

**Step 1: Add integration test**

```python
class TestBuildCasePlanPopulatesTemplates:
    @pytest.mark.asyncio
    async def test_real_build_caseplan_populates_files(self, tmp_path):
        """Integration test: run build_caseplan and verify templates are populated."""
        from caseprep.mcp_server import _handle_build_caseplan
        import asyncio

        topic = "vestibular schwannoma"
        out_dir = tmp_path / "test-caseprep"
        out_dir.mkdir()

        # Run build_caseplan (hits real PubMed API)
        result = await _handle_build_caseplan({
            "topic": topic,
            "max_per_category": 2,
            "output_dir": str(out_dir),
        })

        # Check all files exist
        for name in ["README.md", "anatomy.md", "approach.md", "complications.md", "literature.md"]:
            fpath = out_dir / name
            assert fpath.is_file(), f"Missing: {name}"

        # anatomy.md should NOT be blank - should contain synthesized content OR raw source sentences
        anatomy_text = (out_dir / "anatomy.md").read_text()
        assert "(list relevant structures" not in anatomy_text.lower(), \
            "anatomy.md still has blank placeholder"
        # Should have either synthesized prose or source sentences
        assert len(anatomy_text) > 200, f"anatomy.md too short: {len(anatomy_text)} chars"

        # approach.md should NOT be blank
        approach_text = (out_dir / "approach.md").read_text()
        assert "fill in" not in approach_text.lower(), \
            "approach.md still has blank placeholder"
        assert len(approach_text) > 200, f"approach.md too short: {len(approach_text)} chars"

        # complications.md should NOT be blank
        complications_text = (out_dir / "complications.md").read_text()
        assert "(vascular injury" not in complications_text.lower(), \
            "complications.md still has blank placeholder"
        assert len(complications_text) > 200, f"complications.md too short: {len(complications_text)} chars"

        # At minimum, there should be SOME content in each
        for name, text in [("anatomy.md", anatomy_text), ("approach.md", approach_text), ("complications.md", complications_text)]:
            # Each file should have at least 200 chars of real content (more than just headers)
            content_lines = [l for l in text.split("\n") if l.strip() and not l.startswith("#")]
            assert len(content_lines) >= 3, f"{name} has fewer than 3 content lines"
```

**Step 2: Run integration test**

```bash
cd /home/michael/projects/caseprep && python3 -m pytest tests/test_template_population.py::TestBuildCasePlanPopulatesTemplates -v
```
Expected: PASS (requires network — hits real PubMed).

---

### Task 12: Run full test suite, verify no regressions

```bash
cd /home/michael/projects/caseprep && python3 -m pytest -v
```

Expected: all 79 tests pass (72 existing + 7 new unit tests + 1 integration test).

---

### Task 13: Manual smoke test — generate a case plan and inspect the output

```bash
cd /tmp
python3 -c "
import asyncio, sys
sys.path.insert(0, '/home/michael/projects/caseprep')
from caseprep.mcp_server import _handle_build_caseplan

async def main():
    result = await _handle_build_caseplan({
        'topic': 'retrosigmoid vestibular schwannoma',
        'max_per_category': 3,
        'output_dir': '/tmp/vs-populated-test',
    })
    print(result[:500])

asyncio.run(main())
"
```

Then inspect:
```bash
cat /tmp/vs-populated-test/anatomy.md
cat /tmp/vs-populated-test/approach.md
cat /tmp/vs-populated-test/complications.md
```

Verify each file contains synthesized prose with source citations [S1], [S2], or raw extracted sentences (if LLM was unavailable or guardrails rejected). The output should read as coherent prose, not just scattered bullet points of extracted facts.

---

## Principles Applied

- **DRY:** One `_extract_relevant_sentences` function serves all 3 templates. One `_populate_section` drives the extract→synthesize→guardrail pipeline per template. Keyword lists are data, not duplicated logic.
- **YAGNI:** LLM integration via httpx (already a dependency). Guardrails via stdlib Jaccard similarity (no sentence-transformers, no langchain). Model configurable via env vars.
- **TDD:** Unit tests for extractor, unit tests for guardrails, integration test validates end-to-end pipeline with real PubMed.
- **Bite-sized:** Each task is a single coherent change (collect data → extract → synthesize → guardrail → populate anatomy → populate approach → populate complications → test → verify).
- **Graceful degradation:** Three fallback levels: LLM call fails → raw sentences; guardrails reject → raw sentences; no axis_data → blank templates.

## Verification Checklist

- [ ] `_extract_relevant_sentences` returns sentences when keywords match
- [ ] `_extract_relevant_sentences` returns empty when nothing matches
- [ ] `_extract_relevant_sentences` respects max_sentences cap
- [ ] `_extract_relevant_sentences` uses structured abstracts, not just plain
- [ ] `synthesize_section` calls LLM and returns markdown (requires API key)
- [ ] `verify_synthesis` passes supported claims (Jaccard ≥ 0.15)
- [ ] `verify_synthesis` flags hallucinated claims (Jaccard < 0.15)
- [ ] `verify_synthesis` rejects output when >30% of claims flagged
- [ ] `_populate_section` falls back to raw sentences on LLM failure
- [ ] `_populate_section` falls back to raw sentences on guardrail rejection
- [ ] `anatomy.md` contains synthesized prose OR raw extracted sentences after build_caseplan
- [ ] `approach.md` contains synthesized prose OR raw extracted sentences after build_caseplan
- [ ] `complications.md` contains synthesized prose OR raw extracted sentences after build_caseplan
- [ ] `literature.md` and `README.md` are unchanged (no regression)
- [ ] All existing 72 tests still pass
- [ ] New guardrail tests pass (5 tests)
- [ ] New extractor tests pass (7 tests)
- [ ] Integration test passes (1 test — requires network)
- [ ] Manual inspection of output shows coherent prose, not just scattered facts
