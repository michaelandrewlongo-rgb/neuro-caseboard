import { describe, it, expect } from "vitest"
import { advanceStep, stepStates, formatElapsed } from "./loaderSteps"

describe("advanceStep (monotonic clamp — never wraps backward)", () => {
  it("advances by one within range", () => {
    expect(advanceStep(0, 4)).toBe(1)
    expect(advanceStep(1, 4)).toBe(2)
  })

  it("clamps at total-1 instead of wrapping to 0 (the anti-backward guard)", () => {
    expect(advanceStep(3, 4)).toBe(3)
    // Calling repeatedly on the last step holds — it never returns 0.
    expect(advanceStep(advanceStep(3, 4), 4)).toBe(3)
  })

  it("advanceStep(total-1, total) === total-1 for assorted totals", () => {
    for (const total of [1, 2, 3, 4, 7]) {
      expect(advanceStep(total - 1, total)).toBe(total - 1)
    }
  })
})

describe("stepStates (done / active / pending)", () => {
  it("marks indices before current done, current active, after pending", () => {
    expect(stepStates(4, 2)).toEqual(["done", "done", "active", "pending"])
  })

  it("at index 0 only the first step is active", () => {
    expect(stepStates(3, 0)).toEqual(["active", "pending", "pending"])
  })

  it("handles the single-step edge case", () => {
    expect(stepStates(1, 0)).toEqual(["active"])
  })
})

describe("formatElapsed (live loader stopwatch)", () => {
  it("formats sub-minute as 0:SS with a zero-padded seconds field", () => {
    expect(formatElapsed(0)).toBe("0:00")
    expect(formatElapsed(7)).toBe("0:07")
  })
  it("rolls over into minutes", () => {
    expect(formatElapsed(83)).toBe("1:23")
    expect(formatElapsed(114)).toBe("1:54")
  })
  it("floors fractional seconds and clamps negatives to 0:00", () => {
    expect(formatElapsed(12.9)).toBe("0:12")
    expect(formatElapsed(-5)).toBe("0:00")
  })
})
