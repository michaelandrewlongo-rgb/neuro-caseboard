import { describe, it, expect } from "vitest"
import { heroGridColumns, planningHasData } from "./heroPanels"

describe("heroGridColumns (Dossier hero reflow)", () => {
  it("maps visible-panel count to grid template columns", () => {
    expect(heroGridColumns(0)).toBe("")
    expect(heroGridColumns(1)).toBe("minmax(0, 460px)")
    expect(heroGridColumns(2)).toBe("1fr 1fr")
    expect(heroGridColumns(3)).toBe("1.15fr 1fr 1.05fr")
  })

  it("treats more than three panels as the three-column layout", () => {
    expect(heroGridColumns(4)).toBe("1.15fr 1fr 1.05fr")
  })
})

describe("planningHasData (honest hide-when-empty)", () => {
  it("is false when every planning field is absent", () => {
    expect(planningHasData({})).toBe(false)
  })

  it("is true when any planning field is present", () => {
    expect(planningHasData({ gtr: 80 })).toBe(true)
    expect(planningHasData({ facialPres: 95 })).toBe(true)
    expect(planningHasData({ orTimeHr: 4 })).toBe(true)
  })
})
