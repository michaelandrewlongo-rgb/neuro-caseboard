import { describe, it, expect } from "vitest"
import { shouldShowNavSearch } from "./navSearch"

describe("shouldShowNavSearch (one canonical corpus input)", () => {
  it("hides the nav command field on the Ask route (the page owns the input)", () => {
    expect(shouldShowNavSearch("/ask")).toBe(false)
  })
  it("hides it on nested Ask routes too", () => {
    expect(shouldShowNavSearch("/ask/anything")).toBe(false)
  })
  it("shows it on every other route", () => {
    expect(shouldShowNavSearch("/")).toBe(true)
    expect(shouldShowNavSearch("/build")).toBe(true)
    expect(shouldShowNavSearch("/cards")).toBe(true)
  })
})
