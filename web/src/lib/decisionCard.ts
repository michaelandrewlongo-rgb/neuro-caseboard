// Pure helpers for the Decision Card render (SP2). Kept separate from the JSX so the
// decision-changing logic — why a claim is uncertain, whether the card is worth showing — is unit
// tested without a DOM. The component stays a thin presenter over these.
import type { Citation, DecisionCard, ReviewedClaim } from "./api"

/** Human-readable reason a claim was routed to the amber "uncertain" lane. */
export function claimReason(claim: ReviewedClaim): string {
  const parts: string[] = []
  if (claim.flags.includes("stale_currency")) {
    parts.push(
      claim.year
        ? `asserts current practice but rests on a ${claim.year} source`
        : `asserts a "latest / newly approved" claim with no dated study behind it`,
    )
  }
  if (claim.flags.includes("unmatched_span")) {
    parts.push("the cited source does not verbatim support this claim")
  }
  return parts.join("; ")
}

/** URL of the rendered folio for a textbook [n] marker, or null. Only plain-integer markers
 *  (textbook citations) resolve to a page image; [L#]/[D#] are journal articles (link out). */
export function pageImageUrl(marker: string, sources: Citation[]): string | null {
  if (!/^\d+$/.test(marker)) return null
  const c = sources.find((s) => s.n === Number(marker))
  if (!c || !c.book || c.page == null) return null
  return `/api/page-image?book=${encodeURIComponent(c.book)}&page=${c.page}`
}

/** The first of a claim's markers that resolves to a page image, or null. */
export function firstPageUrl(markers: string[], sources: Citation[]): string | null {
  for (const m of markers) {
    const u = pageImageUrl(m, sources)
    if (u) return u
  }
  return null
}

/** The card is worth rendering only if at least one lane is populated. */
export function hasCardContent(card: DecisionCard): boolean {
  return (
    card.bottom_line.length > 0 ||
    card.decision_furniture.length > 0 ||
    card.uncertainties.length > 0 ||
    card.coverage_gaps.length > 0 ||
    card.conflicts.length > 0
  )
}
