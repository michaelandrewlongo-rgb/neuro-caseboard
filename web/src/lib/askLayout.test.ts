import { describe, it, expect } from "vitest"
import { auditSummaryLabel, shouldRenderLiterature, verificationWarning } from "./askLayout"
import type { Verification } from "./askStore"

function ver(p: Partial<Verification>): Verification {
  return { n_cited_claims: 1, n_unsupported: 0, groundedness: 1, unsupported_markers: [], ...p }
}

describe("verificationWarning (surface the verifier verdict to the reader)", () => {
  it("returns null when nothing is flagged", () => {
    expect(verificationWarning(ver({}))).toBeNull()
    expect(verificationWarning(null)).toBeNull()
  })
  it("lists entailment-failed markers", () => {
    const w = verificationWarning(ver({ n_unsupported: 1, unsupported_markers: ["1"] }))
    expect(w).toEqual({ unsupportedMarkers: ["1"], danglingMarkers: [] })
  })
  it("separates dangling markers from entailment failures (honest wording)", () => {
    // backend unsupported_markers includes dangling ones; the banner must split them so a dangling
    // marker is labeled "not in the source list", not "not entailed".
    const w = verificationWarning(ver({
      n_unsupported: 1, unsupported_markers: ["1", "9"], dangling_markers: ["9"],
    }))
    expect(w).toEqual({ unsupportedMarkers: ["1"], danglingMarkers: ["9"] })
  })
  it("flags a pure dangling marker even if no entailment failures", () => {
    const w = verificationWarning(ver({
      n_unsupported: 1, unsupported_markers: ["7"], dangling_markers: ["7"],
    }))
    expect(w).toEqual({ unsupportedMarkers: [], danglingMarkers: ["7"] })
  })
})

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
