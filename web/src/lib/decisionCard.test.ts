import { describe, it, expect } from "vitest"
import { claimReason, hasCardContent } from "./decisionCard"
import type { DecisionCard, ReviewedClaim } from "./api"

const claim = (over: Partial<ReviewedClaim>): ReviewedClaim => ({
  text: "x", markers: ["1"], category: "other", quote: "", span_matched: true,
  status: "settled", flags: [], year: null, ...over,
})

const emptyCard: DecisionCard = {
  prose: "", bottom_line: [], decision_furniture: [], uncertainties: [],
  coverage_gaps: [], conflicts: [],
}

describe("claimReason", () => {
  it("names the year for a stale dated claim", () => {
    expect(claimReason(claim({ flags: ["stale_currency"], year: 2018 }))).toContain("2018")
  })

  it("explains a stale undated strong-cue claim", () => {
    expect(claimReason(claim({ flags: ["stale_currency"], year: null }))).toContain("no dated study")
  })

  it("explains an unmatched span", () => {
    expect(claimReason(claim({ flags: ["unmatched_span"] }))).toContain("does not verbatim support")
  })

  it("joins multiple flags", () => {
    const r = claimReason(claim({ flags: ["stale_currency", "unmatched_span"], year: 2019 }))
    expect(r).toContain("2019")
    expect(r).toContain("verbatim")
  })
})

describe("hasCardContent", () => {
  it("is false for an empty card", () => {
    expect(hasCardContent(emptyCard)).toBe(false)
  })

  it("is true when any lane is populated", () => {
    expect(hasCardContent({ ...emptyCard, coverage_gaps: ["did not address: beta"] })).toBe(true)
  })
})
