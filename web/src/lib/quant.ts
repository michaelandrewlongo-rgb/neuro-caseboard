/**
 * Quantitative outcome extraction for Build dossiers (BACKLOG P5 #15).
 *
 * Pure regex/parse over claim text — never fabricates a number; only surfaces values literally
 * present — so a dossier can show a "By the numbers" outcome summary (rates, denominators, CIs,
 * p-values, follow-up). Mirrors the Ask-side app/quant_support.py extractor.
 */
export type MetricKind = "percent" | "count" | "interval" | "pvalue" | "duration" | "ratio"

export interface Metric {
  value: string
  kind: MetricKind
  /** Source-claim text the value was extracted from (grounding context). Undefined for 1-arg calls. */
  context?: string
}

const PATTERNS: [MetricKind, RegExp][] = [
  ["count", /\bn\s?=\s?\d+\b/gi],
  ["interval", /\b(?:95\s?%\s?CI|\d{1,3}(?:\.\d+)?\s?%?\s?CI)\b/gi],
  ["pvalue", /\bp\s?[<>=]\s?0?\.\d+\b/gi],
  ["percent", /\b\d{1,3}(?:\.\d+)?\s?%/g],
  ["duration", /\b\d+(?:\.\d+)?\s?(?:day|week|month|year)s?\b/gi],
  ["ratio", /\b\d+(?:\.\d+)?\s?(?:to|\/)\s?\d+(?:\.\d+)?\b/gi],
]

/**
 * Extract metrics from one text, de-duplicated by (kind, value), in pattern then source order.
 * Pass `context` (the source-claim text) to tether each value to its claim for grounding.
 */
export function extractMetrics(text: string, context?: string): Metric[] {
  const out: Metric[] = []
  const seen = new Set<string>()
  for (const [kind, re] of PATTERNS) {
    for (const m of text.matchAll(re)) {
      const value = m[0].trim()
      const key = `${kind}:${value.toLowerCase()}`
      if (seen.has(key)) continue
      seen.add(key)
      out.push({ value, kind, context })
    }
  }
  return out
}

/**
 * Aggregate metrics across many claims (the dossier outcome summary). Each item carries the
 * source-claim `context` so every value stays traceable. Dedup by (kind, value) keeps the FIRST
 * occurrence — so a metric retains the context of the first claim it appeared in.
 */
export function summarizeDossier(
  items: Array<{ text: string; context?: string }>,
): { metrics: Metric[]; counts: Record<string, number> } {
  const metrics: Metric[] = []
  const seen = new Set<string>()
  for (const it of items) {
    for (const m of extractMetrics(it.text, it.context)) {
      const key = `${m.kind}:${m.value.toLowerCase()}`
      if (seen.has(key)) continue
      seen.add(key)
      metrics.push(m)
    }
  }
  const counts: Record<string, number> = {}
  for (const m of metrics) counts[m.kind] = (counts[m.kind] ?? 0) + 1
  return { metrics, counts }
}
