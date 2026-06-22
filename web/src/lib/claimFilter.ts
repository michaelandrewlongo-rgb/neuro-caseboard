import type { DossierClaim } from "@/lib/api"

export type ClaimFilter = "all" | "supported" | "verify" | "quarantine"

/** True when a claim's status belongs in the active filter tab. */
export function claimMatchesFilter(status: DossierClaim["status"], filter: ClaimFilter): boolean {
  if (filter === "all") return true
  return status === filter
}

/** Strict subset: only the claims whose status matches the active filter, original order preserved. */
export function subsetClaims<T extends { status: DossierClaim["status"] }>(
  claims: readonly T[],
  filter: ClaimFilter,
): T[] {
  return claims.filter((c) => claimMatchesFilter(c.status, filter))
}
