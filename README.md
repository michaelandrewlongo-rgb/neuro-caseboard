# neuro-caseboard

A unified neurosurgical **case-prep dossier** that combines the best of two existing
projects:

- **CasePrep** — the audited `Explorer → Enricher → Auditor` pipeline that turns a free-text
  case ("C5-6 corpectomy", "left vestibular schwannoma", "awake left-temporal glioma",
  "right carotid endarterectomy") into validated operative question-cards.
- **textbook-rag** — citation-grounded retrieval over textbook PDFs with a figure/visual
  lane (folio-aware citations + rendered page images).

`neuro-caseboard` reuses both as libraries and owns a **rebuilt report/export surface**
(`model` → `compile` → `render_md` / `render_pdf`) that fixes the nine presentation
defects of the legacy exporter:

1. broken `?` glyphs → embedded Unicode font + deterministic ASCII fallback
2. contradictory confidence/evidence readouts → single evidence axis (confidence dropped)
3. noise `[low]` per-section tags → removed
4. missing marker legend → one-line colour-coded legend
5. claim & rationale run together → claim, then an indented `Why:` line
6. over-dense multi-question bullets → checkbox sub-items
7. weak truncated figure captions → complete captions + claim↔figure cross-links, inline
8. dangling "See appendix" → a real, rendered appendix
9. cross-section redundancy → deterministic near-duplicate collapse with cross-references

Every fix is **topic-agnostic** — driven by card metadata and text structure, never
hardcoded clinical phrases — so the dossier generalises across all of neurosurgery.

## Surfaces

One engine, two features, exposed through one CLI and one local web app:

- **CLI** — `caseboard ask "<question>"` for a cited answer + figures, or
  `caseboard build "<topic>" [--pdf] [-o dir]` for a pre-op dossier.
- **Web** — `streamlit run app/streamlit_app.py` opens a single app with **Ask** and
  **Build board** modes over the same engine. Set `APP_PASSWORD` to gate access (no gate
  locally).
- **Briefing PDF** — `neuro_caseboard.briefing_pdf.render_briefing_pdf(result, out, title=...)`
  exports a Q&A result as a PDF styled to the **Neurosurgery Signal** design (dark navy +
  teal/red signal accents, Syne display). Needs the `briefing` extra:
  `pip install -e ".[briefing]" && playwright install chromium`.

### Contemporary Literature (PubMed)

Every `ask` answer is augmented with a synthesized "Contemporary Literature"
section from PubMed (separate `[L#]` / PMID-DOI citations; the textbook answer is
unchanged). Set `NCBI_API_KEY` (or `NCBI_API_KEY_2`) for the higher rate limit.

Env flags: `LITERATURE_RETRIEVAL` (default on), `LITERATURE_RECENCY_YEARS` (7),
`LITERATURE_K` (8), `LITERATURE_CACHE_TTL_DAYS` (14), `LITERATURE_CACHE_DIR`.

## Clinical depth — the Explorer

The *presentation* fixes generalise across all of neurosurgery, but the *clinical content*
of a board is only as good as the question-cards the Explorer produces. To make the
content generalise too, the Explorer is **LLM-first**:

- `explore_llm.py` asks Claude (`claude-opus-4-8`, structured JSON output) to generate
  **case-specific** anatomy/operative/risk cards for the exact procedure — naming the real
  nerves, vessels, steps, complications, and rescue maneuvers — with a system prompt that
  forbids content from other operations/subspecialties. **Requires `ANTHROPIC_API_KEY`.**
- Without a key it **falls back** to caseprep's deterministic rule-based + family-template
  Explorer (rich where a hand-written template exists, generic elsewhere).
- Either way the manifest passes through `guard.py` (`prune_offtarget`), a deterministic
  anti-bleed filter that strips cross-region content (e.g. CPA / posterior-fossa cranial
  nerves on a supratentorial convexity case).

Toggle: set `CASEBOARD_LLM=0` to force the deterministic path, or pass `caseboard build
--no-llm`. Override the model with `CASEBOARD_LLM_MODEL`.

## Layout

```
neuro_caseboard/
  model.py      Dossier / Section / Claim / FigureItem / EvidenceSummary / Appendix
  compile.py    AuditedManifest + [EvidenceRecord] -> Dossier
  captions.py   complete-caption recovery + subspecialty-neutral relevance line
  dedup.py      deterministic near-duplicate claim collapse
  render_md.py  Markdown renderer
  render_pdf.py fpdf2 renderer (embedded Unicode font + ASCII fallback, inline figures)
  board_view.py presenter: Dossier -> (markdown, figures, summary) for the web Build view
  retrieve.py   InProcessTextbookRetriever (+ subprocess fallback)
  pipeline.py   explorer -> enricher -> auditor (reused) -> compile -> render
  cli.py        `caseboard ask "<q>"` · `caseboard build "<topic>" [--pdf] [-o dir]`
```
