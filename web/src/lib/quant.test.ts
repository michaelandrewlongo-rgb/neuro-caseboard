import { describe, it, expect } from "vitest"
import { extractMetrics, summarizeDossier } from "./quant"

describe("quant outcome extraction (BACKLOG P5 #15)", () => {
  it("extracts percentages, counts, p-values and durations", () => {
    const kinds = new Set(
      extractMetrics(
        "Complete occlusion in 85% of patients (n=240). Retreatment 7.5% at 12 months (p<0.01).",
      ).map((m) => m.kind),
    )
    expect(kinds.has("percent")).toBe(true)
    expect(kinds.has("count")).toBe(true)
    expect(kinds.has("pvalue")).toBe(true)
    expect(kinds.has("duration")).toBe(true)
  })

  it("finds no metrics in purely qualitative text", () => {
    expect(extractMetrics("This approach is generally preferred.")).toEqual([])
  })

  it("aggregates de-duplicated metrics across claims with kind counts", () => {
    const { metrics, counts } = summarizeDossier([
      "Occlusion 90% in the cohort.",
      "Occlusion 90% in the cohort.", // duplicate -> counted once
      "Complication rate 3% (n=120).",
    ])
    expect(metrics.length).toBe(3) // 90%, 3%, n=120
    expect(counts.percent).toBe(2)
    expect(counts.count).toBe(1)
  })

  it("never invents numbers — output values are substrings of the input", () => {
    const text = "Functional independence (mRS 0-2) in 47% at 90 days."
    for (const m of extractMetrics(text)) expect(text.includes(m.value)).toBe(true)
  })
})
