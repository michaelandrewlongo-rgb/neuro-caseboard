import { citationSummary } from "@/lib/citationSummary"

/** The Citation Audit donut and the old standalone status line restated the SAME counts.
    We keep ONE source of truth (citationSummary) and surface it as the collapsed <details>
    summary BELOW the answer, so the result leads with the answer instead of the telemetry. */
export function auditSummaryLabel(corpus: number, literature: number): string {
  return `Citation audit — ${citationSummary(corpus, literature)}`
}
