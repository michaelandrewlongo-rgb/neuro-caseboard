import { describe, it, expect } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { createElement } from "react"
import DecisionCard from "./DecisionCard"
import type { DecisionCard as DecisionCardData } from "@/lib/api"

// Render proof without a DOM: renderToStaticMarkup returns the initial-state HTML string. Enough
// to prove the JSX tree renders and the lanes surface their content (quote toggle stays collapsed).
function html(card: DecisionCardData): string {
  return renderToStaticMarkup(createElement(DecisionCard, { card }))
}

const base: DecisionCardData = {
  prose: "p", bottom_line: [], decision_furniture: [], uncertainties: [],
  coverage_gaps: [], conflicts: [],
}

describe("DecisionCard render", () => {
  it("renders nothing for an empty card", () => {
    expect(html(base)).toBe("")
  })

  it("renders the bottom line, the amber uncertain lane, and coverage gaps", () => {
    const out = html({
      ...base,
      bottom_line: [{ text: "Thrombectomy is indicated for LVO.", markers: ["D1"],
                      category: "indication", quote: "q", span_matched: true, status: "settled",
                      flags: [], year: 2023 }],
      uncertainties: [{ text: "This is the latest device.", markers: ["L1"], category: "regulatory",
                        quote: "q2", span_matched: true, status: "uncertain",
                        flags: ["stale_currency"], year: 2018 }],
      coverage_gaps: ["did not address: thrombolysis"],
    })
    expect(out).toContain("Bottom line")
    expect(out).toContain("Thrombectomy is indicated for LVO.")
    expect(out).toContain("(2023)")
    expect(out).toContain("Uncertain")
    expect(out).toContain("2018 source")            // the amber staleness reason
    expect(out).toContain("did not address: thrombolysis")
    expect(out).toContain("show source")            // click-to-source affordance present
  })
})
