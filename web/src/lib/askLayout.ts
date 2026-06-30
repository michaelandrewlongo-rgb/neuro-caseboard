import { citationSummary } from "@/lib/citationSummary"

/** The Citation Audit donut and the old standalone status line restated the SAME counts.
    We keep ONE source of truth (citationSummary) and surface it as the collapsed <details>
    summary BELOW the answer, so the result leads with the answer instead of the telemetry. */
export function auditSummaryLabel(corpus: number, literature: number): string {
  return `Citation audit — ${citationSummary(corpus, literature)}`
}

/** Whether the contemporary-literature block should render at all. In the DEFAULT woven mode the
    backend sends a LiteratureSection with an empty narrative but a populated citations list (the
    [L#] prose is woven into the main answer). The inline [L#] chips link to the #src-literature-N
    anchors that ONLY this block renders, so the block must render whenever there are citations —
    not only when there is narrative prose. (Returning null on empty narrative left those chips
    dangling.) */
export function shouldRenderLiterature(
  literature: { narrative?: string; citations?: unknown[] } | null | undefined,
): boolean {
  if (!literature) return false
  return Boolean(literature.narrative) || (literature.citations?.length ?? 0) > 0
}
