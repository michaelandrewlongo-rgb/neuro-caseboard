# Plan: Radiology Image Pipeline — Hardening + Next Phase

**Date:** 2026-05-19  
**Context:** Caseprep MCP server has 7 tools, 51 tests passing. Radiology search works end-to-end but has verification gaps. The broader project direction is MCP layer → web delivery layer.

---

## Goal

Harden the radiology image pipeline so a surgeon can trust what comes back, then wire it into the planned web UI.

---

## Part 1: Radiology Verification Gaps (do first)

### 1.1 Validate downloaded images are real image files

**Problem:** Tests verify the file was written and has the right extension, but a 0-byte file or corrupted header would pass. Open-i could serve a 200 response with HTML error body + image/png content-type.

**Fix:** Add `_validate_image()` check in `_download_images()` after writing the file.

```python
# In _download_images(), after filepath.write_bytes():
if not _validate_image(filepath):
    filepath.unlink(missing_ok=True)
    r["local_path"] = "Error: invalid image data"
    continue
```

**File:** `caseprep/mcp_server.py` — new helper `_validate_image(path) -> bool`

Implementation options (pick one):
- (a) Check first 8 bytes against known magic numbers: PNG `\x89PNG`, JPEG `\xff\xd8\xff`, GIF `GIF8`. Zero-dependency, fast.
- (b) `PIL.Image.open(path).verify()` — catches corruption but adds Pillow dependency.

Recommend (a) — zero new deps, covers 99% of Open-i output (PNG + JPEG only).

**Tests:** `tests/test_radiology.py`
- Test valid PNG bytes → passes validation, file stays
- Test valid JPEG bytes → passes validation, file stays
- Test garbage bytes with .png extension → fails validation, file deleted, `local_path` = "Error: invalid image data"
- Test empty file → fails validation

### 1.2 Integration test against live Open-i API

**Problem:** All 16 radiology tests mock HTTP. If Open-i changes its JSON shape, code silently returns empty results. Today's outage proved this — the API was down and we couldn't tell if our code was wrong or the service was dead.

**Fix:** Add `tests/test_radiology_live.py` with `@pytest.mark.integration` marker. Only runs when `OPENI_TEST=1` env var is set.

```python
@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENI_TEST"), reason="Set OPENI_TEST=1 to run")
class TestLiveOpenI:
    async def test_search_returns_results(self):
        results, total = await _openi_search("vestibular schwannoma", max_results=3)
        assert total > 0
        assert len(results) > 0
        assert results[0]["title"]  # non-empty title

    async def test_result_schema_matches_expectation(self):
        results, _ = await _openi_search("schwannoma MRI", max_results=1)
        if results:
            r = results[0]
            for key in ("uid", "title", "caption", "img_large", "img_thumb"):
                assert key in r, f"missing key: {key}"

    async def test_download_produces_valid_file(self):
        results, _ = await _openi_search("schwannoma MRI", max_results=1, query_terms=["schwannoma","mri"])
        if results:
            with tempfile.TemporaryDirectory() as tmpdir:
                results = await _download_images(results, Path(tmpdir), max_images=1)
                local = results[0].get("local_path", "")
                if local and not local.startswith("Error"):
                    assert Path(local).exists()
                    assert Path(local).stat().st_size > 100
```

**File:** `tests/test_radiology_live.py` (new)

**Config:** Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = ["integration: live API tests (set OPENI_TEST=1)"]
```

### 1.3 Adversarial query term filtering

**Problem:** The post-filter is bag-of-words. "CPA angle" could match on "angle" in a dental X-ray caption like "angle of mandible fracture".

**Fix:** Two improvements:

(a) **Add anatomical context boost** — if a query term is found in title, weight it higher than a caption-only match. Currently they're equal. Change the filter to: title match always passes; caption-only match passes only if the term is ≥ 4 chars (filters out "ct", "mri" type ambiguous short terms from being caption-only gateways).

Actually, this is overengineering. The simpler fix:

(b) **Require title match when query_terms ≤ 2** — if the user gave a specific 2-word query like "schwannoma MRI", both terms should appear in the title OR at least one in the title. Captions are too unreliable for short queries.

Better yet — just document the current behavior clearly and add adversarial test cases to lock in the known behavior before changing it:

**File:** `tests/test_radiology.py`
```python
class TestRelevanceFilterEdgeCases:
    @pytest.mark.asyncio
    async def test_short_term_caption_only_match(self):
        """A 2-char term like 'ct' matching only in caption
        should still pass (current behavior) — test locks it in."""
        # ... mock data with "ct" only in caption ...

    @pytest.mark.asyncio
    async def test_unrelated_angle_mention(self):
        """'angle' in 'angle of mandible' shouldn't help a
        CPA angle query — but currently it does. Test documents this."""
        # ... mock data showing the gap ...
```

This documents the known gap without prematurely over-constraining. Fix the algorithm later once we have real usage data.

---

## Part 2: Wire Radiology into `build_caseplan` (the missing connection)

**Problem:** `build_caseplan` runs 4 PubMed searches and writes templates, but it never calls `search_radiology`. A case plan about "vestibular schwannoma" should automatically pull relevant MRI/CT images.

**Fix:** Add a 5th search axis to `_handle_build_caseplan()`:

```python
searches = [
    ("Outcomes / Evidence",      f"{topic} outcomes",                "therapy"),
    ("Surgical Technique",       f"{topic} surgical technique",      None),
    ("Complications",            f"{topic} complications adverse",   "etiology"),
    ("Reviews / Landmarks",      topic,                              "systematic_review"),
    # NEW:
    ("Radiology / Key Images",   topic,                              None),  # calls radiology
]
```

In the loop, detect the radiology axis and call `_handle_radiology()` instead of `_pubmed_search()`. Save downloaded images to `<slug>-caseprep/images/`.

**File:** `caseprep/mcp_server.py` — `_handle_build_caseplan()`, lines 785-845

**Tests:** `tests/test_radiology.py` or new `tests/test_caseplan_integration.py`
- Mock `_openi_search` + `_download_images`, verify the 5th axis runs
- Verify images are saved to `<slug>-caseprep/images/`
- Verify the output includes a "Radiology / Key Images" section

---

## Part 3: Web Delivery Layer (next big phase)

This is the planned FastAPI + JS frontend. Prerequisite: Parts 1-2 are done so the web layer wraps stable, tested functions.

### 3.1 FastAPI backend

**New file:** `caseprep/web.py`

```python
# FastAPI app wrapping existing _handle_* functions
app = FastAPI(title="CasePrep")

@app.post("/api/search")
async def search(topic: str, ...):
    # calls _handle_build_caseplan internally
    ...

@app.post("/api/radiology")
async def radiology(query: str, ...):
    # calls _handle_radiology internally
    ...

@app.get("/api/caseplan/{slug}")
async def get_caseplan(slug: str):
    # reads from SQLite or filesystem
    ...
```

All business logic stays in `mcp_server.py`. `web.py` is a thin transport adapter (HTTP ↔ MCP handler). Same pattern as the existing MCP transport layer — the handlers don't know or care how they're called.

### 3.2 SQLite persistence

**New file:** `caseprep/db.py`

Store case plans + search history. Schema:
- `caseplans` table: id, topic, slug, created_at, output_dir
- `papers` table: pmid, title, journal, doi, abstract, caseplan_id (FK)
- `images` table: uid, pmid, local_path, caption, caseplan_id (FK)

### 3.3 Frontend

**New file:** `caseprep/static/index.html` + JS

Minimal interactive dashboard:
- Topic input → POST /api/search → show expandable paper cards
- "View Images" button per paper → inline radiology display
- Search history sidebar (from SQLite)

### 3.4 CLI command

**File:** `caseprep/cli.py` — add `caseprep serve` subcommand

```python
@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000):
    """Launch the CasePrep web dashboard."""
    uvicorn.run("caseprep.web:app", host=host, port=port)
```

---

## Execution Order

| Step | What | Depends on | Est. effort |
|------|------|------------|-------------|
| 1 | Image validation helper + tests | Nothing | 30 min |
| 2 | Live integration test file | Nothing | 15 min |
| 3 | Adversarial filter edge-case tests | Nothing | 20 min |
| 4 | Wire radiology into build_caseplan | Steps 1-3 | 45 min |
| 5 | FastAPI backend (web.py) | Step 4 | 2-3 hr |
| 6 | SQLite persistence (db.py) | Step 5 | 1 hr |
| 7 | Frontend (index.html + JS) | Steps 5-6 | 2-3 hr |
| 8 | `caseprep serve` CLI command | Step 7 | 30 min |

---

## Risks & Tradeoffs

1. **Open-i instability** — The API was down today. The web UI needs a graceful degradation path when radiology search fails (show papers, show "images unavailable" badge, not a crash).
2. **Image validation: magic numbers vs Pillow** — Magic numbers are fast and zero-dep but won't catch a truncated PNG. Pillow catches corruption but adds a dependency. Recommendation: start with magic numbers, add Pillow later if we see real corruption in production.
3. **Post-filter is coarse** — The bag-of-words relevance filter will have false positives (e.g. "angle" matching dental X-rays). Document it. Don't over-fit to edge cases before we have real usage data.
4. **Web layer scope creep** — Easy to over-build the frontend. Start with the minimal: topic input → results. No auth, no accounts, no bookmarks in v1. SQLite for persistence. Add features based on what real users ask for.

## Open Questions

- Should the web UI require API keys (NCBI, Resend) server-side or per-user? Recommendation: server-side pooled keys for v1 (simpler for doctors). Environment-configured.
- Should radiology images be served by FastAPI (static files) or via presigned URLs? Recommendation: FastAPI `StaticFiles` mount for v1.
- What model serves the web layer's "AI summary" feature if we add one? Deferred — not in this plan.
