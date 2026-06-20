import { describe, it, expect } from "vitest"
import {
  cardsQueryReducer,
  initialCardsQuery,
  type CardsQueryState,
} from "./cardsQuery"

describe("cardsQuery reducer (BACKLOG P4 #11 input-state sync)", () => {
  it("selecting a chip makes the visible input equal the chip text", () => {
    const s = cardsQueryReducer(initialCardsQuery, {
      type: "selectChip",
      text: "cavernous sinus contents",
    })
    expect(s.question).toBe("cavernous sinus contents")
  })

  it("typing replaces the value and never appends to stale chip text", () => {
    let s: CardsQueryState = cardsQueryReducer(initialCardsQuery, {
      type: "selectChip",
      text: "cavernous sinus contents",
    })
    // user clears and types something new — must REPLACE, not append
    s = cardsQueryReducer(s, { type: "type", text: "circle of willis" })
    expect(s.question).toBe("circle of willis")
  })

  it("clearing empties the visible input (no hidden residue)", () => {
    let s = cardsQueryReducer(initialCardsQuery, { type: "type", text: "abc" })
    s = cardsQueryReducer(s, { type: "clear" })
    expect(s.question).toBe("")
  })

  it("submit derives submitted from the current question (trimmed)", () => {
    let s = cardsQueryReducer(initialCardsQuery, { type: "type", text: "  vertebral artery  " })
    s = cardsQueryReducer(s, { type: "submit" })
    expect(s.submitted).toBe("vertebral artery")
    expect(s.question).toBe("  vertebral artery  ") // input untouched; submitted is derived
  })

  it("resubmission after editing uses the new text, not the old chip", () => {
    let s = cardsQueryReducer(initialCardsQuery, { type: "selectChip", text: "old chip" })
    s = cardsQueryReducer(s, { type: "submit" })
    expect(s.submitted).toBe("old chip")
    // user edits then resubmits
    s = cardsQueryReducer(s, { type: "type", text: "new query" })
    s = cardsQueryReducer(s, { type: "submit" })
    expect(s.submitted).toBe("new query")
    expect(s.question).toBe("new query")
  })
})
