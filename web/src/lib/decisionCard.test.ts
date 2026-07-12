import { describe, it, expect } from "vitest"
import { claimReason, firstPageUrl, hasCardContent, pageImageUrl } from "./decisionCard"
import type { Citation, DecisionCard, ReviewedClaim } from "./api"

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

const sources: Citation[] = [
  { n: 1, book: "Youmans and Winn", chapter: "Ch419", page: 5710, location: "Youmans, Ch419, p.5710" },
]

describe("pageImageUrl", () => {
  it("builds a page URL for a textbook marker", () => {
    expect(pageImageUrl("1", sources)).toBe("/api/page-image?book=Youmans%20and%20Winn&page=5710")
  })

  it("returns null for literature / corpus markers", () => {
    expect(pageImageUrl("L1", sources)).toBeNull()
    expect(pageImageUrl("D2", sources)).toBeNull()
  })

  it("returns null when no source matches the marker", () => {
    expect(pageImageUrl("9", sources)).toBeNull()
  })
})

describe("firstPageUrl", () => {
  it("picks the first resolvable marker", () => {
    expect(firstPageUrl(["L1", "1"], sources)).toContain("page=5710")
  })

  it("is null when no marker resolves", () => {
    expect(firstPageUrl(["L1", "D2"], sources)).toBeNull()
  })
})
