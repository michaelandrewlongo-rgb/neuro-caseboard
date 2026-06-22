import { describe, it, expect } from "vitest"
import type { DossierClaim } from "./api"
import { claimMatchesFilter, subsetClaims, type ClaimFilter } from "./claimFilter"

type Status = DossierClaim["status"]

const STATUSES: Status[] = ["supported", "verify", "quarantine"]
const FILTERS: ClaimFilter[] = ["all", "supported", "verify", "quarantine"]

describe("claimMatchesFilter (loop step 1: quarantine + strict subset)", () => {
  it("matches every status under the 'all' filter", () => {
    for (const status of STATUSES) {
      expect(claimMatchesFilter(status, "all")).toBe(true)
    }
  })

  it("matches a status under a non-'all' filter only when status === filter", () => {
    for (const status of STATUSES) {
      for (const filter of FILTERS) {
        const expected = filter === "all" ? true : status === filter
        expect(claimMatchesFilter(status, filter)).toBe(expected)
      }
    }
  })

  it("matches quarantine ONLY under the 'quarantine' and 'all' filters", () => {
    expect(claimMatchesFilter("quarantine", "quarantine")).toBe(true)
    expect(claimMatchesFilter("quarantine", "all")).toBe(true)
    expect(claimMatchesFilter("quarantine", "supported")).toBe(false)
    expect(claimMatchesFilter("quarantine", "verify")).toBe(false)
  })
})

describe("subsetClaims", () => {
  const claims: { status: Status; id: number }[] = [
    { status: "supported", id: 0 },
    { status: "verify", id: 1 },
    { status: "quarantine", id: 2 },
    { status: "supported", id: 3 },
    { status: "verify", id: 4 },
  ]

  it("returns only matching claims and preserves original order", () => {
    expect(subsetClaims(claims, "supported").map((c) => c.id)).toEqual([0, 3])
    expect(subsetClaims(claims, "verify").map((c) => c.id)).toEqual([1, 4])
    expect(subsetClaims(claims, "quarantine").map((c) => c.id)).toEqual([2])
  })

  it("returns the full list under 'all'", () => {
    expect(subsetClaims(claims, "all")).toEqual(claims)
  })

  it("returns [] when nothing matches", () => {
    const onlySupported: { status: Status }[] = [{ status: "supported" }, { status: "supported" }]
    expect(subsetClaims(onlySupported, "quarantine")).toEqual([])
  })
})

describe("subsetClaims partition invariant (tab counts == rendered claims)", () => {
  // Build.tsx derives tab counts from the post-dedup claims flattened across all sections.
  // The fix relies on: summing subsetClaims over each section equals subsetClaims over the
  // flattened union, for every filter — so a per-section render can never disagree with the
  // tab count regardless of how claims are distributed across sections.
  const sections: { claims: { status: Status }[] }[] = [
    { claims: [{ status: "supported" }, { status: "quarantine" }] },
    { claims: [{ status: "verify" }, { status: "supported" }, { status: "verify" }] },
    { claims: [] },
    { claims: [{ status: "quarantine" }, { status: "supported" }] },
  ]
  const flattened = sections.flatMap((s) => s.claims)

  it("sum over sections equals the flattened subset for every filter", () => {
    for (const filter of FILTERS) {
      const perSection = sections.reduce((n, s) => n + subsetClaims(s.claims, filter).length, 0)
      expect(perSection).toBe(subsetClaims(flattened, filter).length)
    }
  })
})
