import { describe, it, expect } from "vitest"
import { citationSummary } from "./citationSummary"

describe("citationSummary (lane-honest Ask status line)", () => {
  it("reports no citations when both lanes are empty", () => {
    expect(citationSummary(0, 0)).toBe("No citations in this response")
  })

  it("names only the textbook corpus when there is no literature", () => {
    expect(citationSummary(16, 0)).toBe("16 citations from your textbook corpus")
  })

  it("names both lanes by source when literature is present", () => {
    expect(citationSummary(16, 12)).toBe("28 citations · 16 textbook corpus · 12 PubMed literature")
  })

  it("uses the singular noun for a single citation", () => {
    expect(citationSummary(1, 0)).toBe("1 citation from your textbook corpus")
  })

  it("still names both lanes when only literature is present", () => {
    expect(citationSummary(0, 3)).toBe("3 citations · 0 textbook corpus · 3 PubMed literature")
  })
})
