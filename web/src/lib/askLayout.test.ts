import { describe, it, expect } from "vitest"
import { auditSummaryLabel, shouldRenderLiterature } from "./askLayout"

describe("shouldRenderLiterature (default woven mode has citations but no narrative)", () => {
  it("renders when there are citations even though the narrative is empty (woven default)", () => {
    // Backend woven mode emits LiteratureSection(narrative="", citations=[…]); the inline [L#]
    // chips must resolve to a rendered src-literature-N list, so the block MUST render here.
    expect(shouldRenderLiterature({ narrative: "", citations: [{ n: 1 }] })).toBe(true)
  })
  it("renders when there is a narrative (separate-lane mode)", () => {
    expect(shouldRenderLiterature({ narrative: "Some prose [L1].", citations: [] })).toBe(true)
  })
  it("does not render when there is neither narrative nor citations", () => {
    expect(shouldRenderLiterature({ narrative: "", citations: [] })).toBe(false)
  })
  it("does not render for a null/absent literature object", () => {
    expect(shouldRenderLiterature(null)).toBe(false)
    expect(shouldRenderLiterature(undefined)).toBe(false)
  })
})

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
