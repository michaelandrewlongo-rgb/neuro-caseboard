// web/src/lib/api.test.ts
import { describe, expect, it, vi, beforeEach, type Mock } from "vitest"
import { askQuestion, startAsk } from "./api"
import type { AskResponse } from "./api"

describe("Ask answer wire type", () => {
  it("accepts evidence_spans + citation folio fields", () => {
    const r: AskResponse = {
      kind: "answer",
      answer: "Claim [1].",
      citations: [{ n: 1, book: "Youmans", chapter: "Ch419", page: 5710,
                    printed_page: "3357", page_ref: "p.3357", location: "Youmans, Ch419, p.5710" }],
      figures: [],
      literature: null,
      evidence_spans: [{ claim: "Claim [1].", marker: "1", quote: "the sentence",
                         matched: true, score: 1.0 }],
    }
    expect(r.kind === "answer" && r.evidence_spans[0].matched).toBe(true)
    expect(r.kind === "answer" && r.citations[0].page_ref).toBe("p.3357")
  })
})

describe("Ask request bodies", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(() =>
      Promise.resolve({ json: () => Promise.resolve({ kind: "answer" }) } as Response)))
  })

  it("askQuestion omits cerebrovascular by default", async () => {
    await askQuestion("q")
    const [, init] = (fetch as unknown as Mock).mock.calls[0]
    const body = JSON.parse(init.body as string)
    expect(body.cerebrovascular).toBe(false)
  })

  it("askQuestion sends cerebrovascular=true when passed", async () => {
    await askQuestion("q", undefined, false, true)
    const [, init] = (fetch as unknown as Mock).mock.calls[0]
    const body = JSON.parse(init.body as string)
    expect(body.cerebrovascular).toBe(true)
  })

  it("startAsk sends cerebrovascular=true when passed", async () => {
    vi.stubGlobal("fetch", vi.fn(() =>
      Promise.resolve({ json: () => Promise.resolve({ job_id: "abc" }) } as Response)))
    await startAsk("q", false, true)
    const [, init] = (fetch as unknown as Mock).mock.calls[0]
    const body = JSON.parse(init.body as string)
    expect(body.cerebrovascular).toBe(true)
  })
})
