import { describe, it, expect } from "vitest"
import { figureIsEnlargeable } from "./figures"

describe("figureIsEnlargeable (lightbox affordance predicate)", () => {
  it("is true when image_url present AND image_available", () => {
    expect(figureIsEnlargeable({ image_url: "x.png", image_available: true })).toBe(true)
  })

  it("is false when image_available is false (even with a url)", () => {
    expect(figureIsEnlargeable({ image_url: "x.png", image_available: false })).toBe(false)
  })

  it("is false when image_url is null (even if available)", () => {
    expect(figureIsEnlargeable({ image_url: null, image_available: true })).toBe(false)
  })

  it("is false when both are absent (placeholder figure)", () => {
    expect(figureIsEnlargeable({ image_url: null, image_available: false })).toBe(false)
  })
})
