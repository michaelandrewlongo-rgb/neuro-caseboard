# Plan — P2 #9: context-free "By the Numbers" (attach claim context to each metric)

**Bug:** The Dossier "By the numbers" panel renders bare metric chips — "9–14%", "p<0.05", "n=340" —
with **no indication of what they refer to**. Root cause: `quant.ts::summarizeDossier` flattens all claim
texts and `extractMetrics` returns `{value, kind}` only, so a metric **loses its source claim**. A
free-floating percentage in a clinical tool invites misreading ("9–14% of *what*?") — it violates the
repo's honest-grounding stance (a number must stay tethered to its claim).

**Fix (backlog's "attach claim context"):** thread the source-claim context through extraction so every
chip is traceable to the claim it came from, surfaced via `title` (hover) + `aria-label` (SR). The claims
themselves are already rendered in the section cards just below, so the panel stays a compact scan-summary
— now grounded, not context-free. No suppression needed since every metric gains a context.

---

- [ ] **Step 1 — Thread claim context through quant extraction + render it on the chip (frontend only)**
  - `web/src/lib/quant.ts`:
    - `Metric` gains `context?: string` (the source-claim text the value was extracted from).
    - `extractMetrics(text: string, context?: string): Metric[]` — optional 2nd arg; attach `context` to
      each emitted metric (existing 1-arg calls keep working, `context` undefined).
    - `summarizeDossier(items: Array<{ text: string; context?: string }>)` — change the param from
      `string[]` to objects so each claim's context travels with its metrics. Dedup by (kind,value) still,
      keeping the FIRST occurrence (and its context). Pass `it.context` into `extractMetrics(it.text, it.context)`.
  - `web/src/components/build/DossierView.tsx`:
    - Build the input as `dossier.sections.flatMap(s => s.claims.map(c => ({ text: `${c.text} ${c.why}`,
      context: c.text })))` (the claim assertion is the grounding context).
    - On each metric chip add `title={m.context}` and `aria-label={m.context ? `${m.value} — ${m.context}`
      : m.value}` so the number is traceable on hover / to screen readers. Add a one-line caption under the
      "By the numbers" eyebrow like "hover a value for its source claim" (muted-mono) so the affordance is
      discoverable. No other layout change.
  - `web/src/lib/quant.test.ts`:
    - Update the existing `summarizeDossier([...])` test to pass `{text, context}` objects (was bare
      strings).
    - ADD: `extractMetrics("recurrence 9–14%", "Recurrence after GTR")` → each metric has
      `context === "Recurrence after GTR"`. And a `summarizeDossier` test asserting the metric keeps the
      context of its FIRST source claim across dedup.
    - Keep the "never invents numbers" + "no metrics in qualitative text" tests green.
  - **Verify:** `npm --prefix web run test` + `npm --prefix web run build` + `npm --prefix web run lint`.

**Non-regression invariant:** never fabricates — values remain literal substrings of claim text; the only
change is carrying the source claim alongside each value (more grounding, not less). The `app/quant_support.py`
Ask-side mirror is a separate path — out of scope.
