import { citationSummary } from "@/lib/citationSummary"
import type { Verification } from "@/lib/askStore"

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

export interface VerificationWarning {
  unsupportedMarkers: string[] // cited but not entailed by the cited source
  danglingMarkers: string[] // reference a source not in the list (invented/dangling)
  uncitedClinical: number // clinical statements with no citation at all (A2)
}

/** What the answer's needs-verification banner should show, or null when the verifier flagged
    nothing. The backend's `unsupported_markers` already INCLUDES any dangling markers, so we split
    them for honest wording: entailment-failures vs "cites a source not in the list". This mirrors
    the backend's verification_notice so the web banner and the CLI/notice stay consistent. */
export function verificationWarning(
  v: Verification | null | undefined,
): VerificationWarning | null {
  if (!v) return null
  const dangling = v.dangling_markers ?? []
  const unsupported = (v.unsupported_markers ?? []).filter((m) => !dangling.includes(m))
  const uncitedClinical = v.n_uncited_clinical ?? 0
  if (unsupported.length === 0 && dangling.length === 0 && uncitedClinical === 0) return null
  return { unsupportedMarkers: unsupported, danglingMarkers: dangling, uncitedClinical }
}
