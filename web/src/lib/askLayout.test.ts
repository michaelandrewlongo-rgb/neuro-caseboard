import { describe, it, expect } from "vitest"
import { auditSummaryLabel } from "./askLayout"

describe("auditSummaryLabel (collapsed Citation Audit summary)", () => {
  it("composes the lane-honest count line so there is ONE source of truth", () => {
    expect(auditSummaryLabel(17, 12)).toBe(
      "Citation audit — 29 citations · 17 textbook corpus · 12 PubMed literature")
  })
  it("handles a corpus-only response", () => {
    expect(auditSummaryLabel(16, 0)).toBe(
      "Citation audit — 16 citations from your textbook corpus")
  })
  it("handles an empty response", () => {
    expect(auditSummaryLabel(0, 0)).toBe("Citation audit — No citations in this response")
  })
})
