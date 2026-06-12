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

## Layout

```
neuro_caseboard/
  model.py      Dossier / Section / Claim / FigureItem / EvidenceSummary / Appendix
  compile.py    AuditedManifest + [EvidenceRecord] -> Dossier
  captions.py   complete-caption recovery + subspecialty-neutral relevance line
  dedup.py      deterministic near-duplicate claim collapse
  render_md.py  Markdown renderer
  render_pdf.py fpdf2 renderer (embedded Unicode font + ASCII fallback, inline figures)
  retrieve.py   InProcessTextbookRetriever (+ subprocess fallback)
  pipeline.py   explorer -> enricher -> auditor (reused) -> compile -> render
  cli.py        `caseboard build "<topic>" [--pdf] [-o dir]`
```
