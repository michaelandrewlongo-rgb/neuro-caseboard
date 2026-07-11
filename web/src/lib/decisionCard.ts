// Pure helpers for the Decision Card render (SP2). Kept separate from the JSX so the
// decision-changing logic — why a claim is uncertain, whether the card is worth showing — is unit
// tested without a DOM. The component stays a thin presenter over these.
import type { DecisionCard, ReviewedClaim } from "./api"

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
