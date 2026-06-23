# Plan — P3 #13: ambiguous grounding copy (literature implied ungrounded)

**Bug:** The Ask status line reads "16 OF 28 CITATIONS FROM GROUNDED CORPUS · 12 FROM LITERATURE"
(`Ask.tsx:125`) and the Citation Audit gauge shows "{grounded}/{total}" under a "GROUNDED" label
(`CitationAudit.tsx:59,65`). Both frame the **textbook-corpus** count as "grounded" against the total, so
the 12 PubMed **literature** citations read as *ungrounded* — a category error. Literature `[L#]` citations
are real, verifiable sources (PMIDs); they're a different LANE (live PubMed vs entailment-gated textbook
corpus), not fabrications. The project's actual invariant is **zero fabricated citations** — true of both
lanes. Reword to name both lanes by source and stop implying one is ungrounded.

---

- [x] **Step 1 — Lane-honest citation copy (frontend only)**
  - `web/src/lib/citationSummary.ts` (NEW, pure, no React): build the status string so the logic is
    testable.
    ```ts
    export function citationSummary(corpus: number, literature: number): string {
      const total = corpus + literature
      if (total === 0) return "No citations in this response"
      const noun = total === 1 ? "citation" : "citations"
      if (literature === 0) return `${total} ${noun} from your textbook corpus`
      return `${total} ${noun} · ${corpus} textbook corpus · ${literature} PubMed literature`
    }
    ```
    (Names both lanes by source; drops the "grounded vs not" framing; pluralizes "citation".)
  - `web/src/lib/citationSummary.test.ts` (NEW): total 0 → "No citations…"; literature 0 →
    "N citations from your textbook corpus"; literature > 0 → "T citations · C textbook corpus · L PubMed
    literature"; singular total 1 → "1 citation …" (pluralization).
  - `web/src/pages/Ask.tsx` (~120-126): replace the inline IIFE string with
    `{citationSummary(resp.citations.length, resp.literature?.citations.length ?? 0)}`.
  - `web/src/components/ask/CitationAudit.tsx`:
    - Gauge center (`:59,65`): change `{grounded}/{total}` → `{total}` and the label `GROUNDED` → `CITED`
      (the rings + legend already show the corpus/literature split; the lone "grounded/total" was the
      misleading bit). Keep the two rings.
    - Legend (`:77,86`): keep the colored breakdown but clarify the labels — `Corpus (n)` →
      `Textbook corpus (n)`, `Literature (n)` → `PubMed literature (n)` — matching the status-line wording.
    - Update the doc-comment (`:6-7`): "not from the grounded corpus" → "from the live PubMed lane (a
      separate evidence lane from the textbook corpus)" so the code comment doesn't repeat the category
      error. No data/count change — `grounded`/`toLit`/`total` variables stay; only labels/comments reword.
  - **Verify:** `npm --prefix web run test` (incl new citationSummary spec) + `npm --prefix web run build`
    + `npm --prefix web run lint`.

**Scope guard:** #13 only — the grounding copy. NOT the "1 papers" pluralization elsewhere (#14) or the
quant panel (#9, merged). (This slice does pluralize "1 citation" in the status line since it owns that
string.)

**Non-regression:** counts are unchanged and still derived from real `AskResponse` fields (no fabrication);
only the wording/labels change. Honest invariant strengthened — the copy no longer implies real PubMed
citations are ungrounded, while NOT overclaiming they passed the corpus entailment gate (they're named as a
distinct "PubMed literature" lane).
