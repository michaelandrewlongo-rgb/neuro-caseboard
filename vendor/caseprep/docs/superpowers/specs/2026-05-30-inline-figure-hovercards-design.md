# Inline Figure Hovercards for the Briefing — Design

**Date:** 2026-05-30
**Status:** Approved design, ready for implementation plan
**Program:** Neuro-IR briefing completeness — image integration
**Scope:** Wire both figure sources (`image_bank` + `textbook_figures`) into the
briefing as inline, hover-to-reveal figures. Thrombectomy is the first family.

## Problem

The briefing is text-only. The project has two rich figure corpora that are
disconnected from it:

- **`image_bank`** — `caseprep/image_bank/bank.db` (~20k PMC figures). Local
  SQLite. `images` + `labels` tables give each figure keyword **tags**
  (`keywords`, `anatomy`, `pathology`, `procedure`), a caption, a local image
  file (`local_path`), and a citation (`pmcid`/`pmid`). **No embeddings.**
- **`textbook_figures`** — in the Postgres/pgvector corpus DB. Each row has VLM
  caption (`caption_vlm`), keyword tags (`vlm_keywords`), a `heading_path`
  citation, the image as **bytes in-DB** (`image_data`), and a 768-d
  **embedding** (`all-mpnet-base-v2`).

Goal: when a figure's tags match a word in the briefing, mark that word with a
hoverable superscript; on hover, the single **most semantically relevant** figure
(from either source) pops up large, with its source credited.

## Goals

1. Mark briefing words whose meaning is illustrated by a figure tag (precision
   over recall — no clutter, no wrong figures).
2. On hover, reveal the top-1 figure ranked by semantic relevance to the term's
   surrounding context, drawn from a unified pool of both sources.
3. Every revealed figure is traceable to its source (PMID, or textbook
   `heading_path`).
4. Output a self-contained `briefing.html` artifact alongside the Markdown.
5. Reproducible and offline at briefing-generation time — no live Postgres.

## Non-goals (this cycle)

- A native HTML briefing renderer (we post-process the existing Markdown).
- Re-labeling / re-harvesting either corpus.
- Per-case retrieval tuning beyond top-1 semantic rank.
- Other families' tag vocabularies beyond thrombectomy (registration-only later).

## Key decisions

- **D1 — Two-stage match.** *Tag match* (lexical) decides which words get a
  superscript; *semantic rank* (cosine) decides which single figure shows.
  Mirrors the user's mental model exactly.
- **D2 — Precompute one local figure store, offline.** A one-time build merges
  both sources into a single local index carrying tags, caption, image, citation,
  and a 768-d embedding. `image_bank` captions are **newly embedded** with the
  same `all-mpnet-base-v2` model so both corpora rank in one space;
  `textbook_figures` embeddings + image bytes are **extracted from Postgres**.
  After the build, generation needs no live Postgres and is deterministic.
- **D3 — Post-process Markdown → HTML, don't rebuild the renderer.** Convert the
  existing Markdown briefing to HTML and inject hovercards. Smallest surface,
  reuses the whole pipeline, yields one shareable `briefing.html`.
- **D4 — Precision guardrail.** Mark only *salient* clinical tags (anatomy /
  pathology / procedure terms and multi-word phrases; drop generic/common words
  via a stop-tag filter and a min-salience rule), and only the **first
  occurrence per page** of each term. Below confidence, no marker.
- **D5 — Self-contained output.** Embed the chosen images (base64) in the HTML so
  it is shareable and never shows a broken local path.
- **D6 — Depends on the image-bank infra (PR #4).** That PR is merged to main
  first; this cycle builds on its `ImageIndex` / record conventions.

## Architecture

Four units with narrow interfaces.

### Unit 1 — Unified figure store builder (offline)

`caseprep/image_bank/figure_store.py` (new). `build()`:
- Reads `image_bank` (`images ⋈ labels`, `is_neurosurgical=1`): collects tags
  (`keywords ∪ anatomy ∪ pathology ∪ procedure`), caption, `local_path`,
  `pmcid`/`pmid`. Embeds the caption text (`all-mpnet-base-v2`, 768-d,
  normalized).
- Reads `textbook_figures` from Postgres: collects `vlm_keywords` tags,
  `caption_vlm`/`caption`, `heading_path`, the existing `embedding`, and the
  `image_data` bytes.
- Writes a single local store: a record per figure
  `{source, fig_id, tags[sorted], caption, image_ref, citation, embedding}` plus
  the image bytes/paths. Persisted next to `bank.db` (sidecar:
  `figure_store.sqlite` for records + a vectors file, or one sqlite with a BLOB
  embedding column). Atomic write. Idempotent.
- **Depends on:** `bank.db`, the Postgres corpus, the embedding model. Build-time
  only.

### Unit 2 — Salient tag vocabulary + matcher

`caseprep/figure_tags.py` (new). From the store, derive a **salient tag
vocabulary**: the set of tags eligible to mark words, after filtering
(stop-tags, generic/common-word drop, prefer anatomy/pathology/procedure and
multi-word phrases; family-keyed allow/deny lists so thrombectomy is registered
first and other families register later). `find_marks(text) -> list[Mark]`
returns, for the briefing text, the first-occurrence-per-page spans whose token
matches a salient tag, with the candidate figure ids whose tags include it.
Deterministic, whole-word matching (never inside another word).

### Unit 3 — Semantic ranker

`caseprep/figure_rank.py` (new). `best_figure(term, context, candidates) ->
Figure | None`. Embeds the term's surrounding context (enclosing sentence /
section heading) with the same model, computes cosine vs each candidate's stored
embedding, returns the top-1 above a floor (else `None` → no marker). The
context-embedding model load is the only runtime model dependency; if
unavailable, fall back to highest tag-overlap + `surgical_usefulness` so the
feature still degrades to a sensible figure rather than failing.

### Unit 4 — HTML hovercard renderer

`caseprep/renderers/briefing_html.py` (new). `render_briefing_html(markdown,
schema) -> str`: Markdown → HTML, then for each `Mark` inject a superscript
marker next to the word and a large hover popover containing the figure
(base64-embedded `<img>`), caption, and a source link (PMC for image_bank,
heading for textbook). CSS-driven hover + click; all text escaped. Emits a
self-contained `briefing.html`.

### Touch-point — output artifact

Generation writes `briefing.html` alongside the Markdown files (and/or a CLI/MCP
export). The Markdown briefing is unchanged (stays clean/minimal).

## Data flow

```
(offline build)
  bank.db (images⋈labels)  ─embed captions─┐
  Postgres textbook_figures ─copy embedding,│→ figure_store (local): {source, tags, caption, image, citation, embedding}
                             extract bytes ─┘

(per briefing)
  markdown briefing ─► Unit 2 find_marks (salient tag hit, 1st/page)
                              │  candidates per term
                              ▼
                      Unit 3 best_figure (embed context → cosine top-1, floor)
                              │  chosen figure (or None → no mark)
                              ▼
                      Unit 4 md→html + inject superscript + big hover popover (base64 img + source)
                              ▼
                          briefing.html (self-contained)
```

## Error handling

| Condition | Behavior |
|---|---|
| Figure store missing | No marks injected; HTML = plain converted Markdown. |
| Term matches a tag but no candidate clears the cosine floor | No marker (precision over recall). |
| Chosen figure's image bytes/file missing | Skip it; try next candidate; else no marker. |
| Embedding model unavailable at gen-time | Fall back to tag-overlap + `surgical_usefulness` ranking. |
| Postgres unavailable | Only affects the offline build; generation already uses the local store. |
| Common/generic word | Excluded by the salient-tag filter (never marked). |

## Testing

- **Store build hygiene:** records carry tags+caption+citation+embedding;
  image_bank rows get a 768-d vector; missing-image rows excluded; atomic write.
- **Salient filter:** generic words (e.g. "patient", "left") never enter the
  vocabulary; clinical terms (e.g. "ASPECTS", "tandem occlusion") do; whole-word
  matching (no substring hits); first-occurrence-per-page only.
- **Semantic rank:** given candidates with known embeddings, the highest-cosine
  one is returned; below the floor → `None`; fallback path returns a figure when
  the model is absent.
- **HTML injection:** a marked term renders a superscript + a popover containing
  the figure `<img>` and a source link; an unmatched term stays plain; all
  fields escaped; output is self-contained (no external image refs).
- **Integration:** a thrombectomy briefing with "ASPECTS"/"M1 MCA occlusion"
  yields hovercards sourced from the store, each traceable to a PMID/heading.

## Prerequisites

1. **Merge PR #4** (image-bank infra) to main; branch this cycle from the result.
2. **Run the offline store build** once (needs the Postgres corpus + embedding
   model) to produce the local figure store the generation path consumes.

## Open implementation notes

- Store format (single sqlite with BLOB vectors vs records + `.npy`) settled in
  the plan; both satisfy offline-build + fast local cosine.
- Salient-tag filtering thresholds tuned against a real thrombectomy briefing
  during implementation; start conservative (high precision, low clutter).
- Confirm `textbook_figures.image_data` decodes to displayable images for the
  figures actually surfaced; skip undecodable ones at build time.
- Family-keyed vocab/registries so later families are registration-only.
