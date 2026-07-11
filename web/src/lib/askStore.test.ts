import { describe, it, expect } from "vitest"
import { applyAskEvent, emptyAskState, loadAsk, saveAsk, type AskEvent } from "./askStore"

function feed(events: AskEvent[]) {
  let s = emptyAskState("q", "job1")
  events.forEach((e, i) => {
    s = applyAskEvent(s, e, i)
  })
  return s
}

describe("applyAskEvent", () => {
  it("appends answer deltas and tracks nextIndex", () => {
    const s = feed([
      { type: "sources", citations: [{ n: 1, book: "B", chapter: "C", page: 1, location: "B, C, p.1" }] },
      { type: "figures", figures: [] },
      { type: "answer_delta", text: "Hel" },
      { type: "answer_delta", text: "lo" },
    ])
    expect(s.answer).toBe("Hello")
    expect(s.sources.length).toBe(1)
    expect(s.nextIndex).toBe(4)
  })

  it("ignores events already seen (dedup on restore)", () => {
    let s = emptyAskState("q", "job1")
    s = applyAskEvent(s, { type: "answer_delta", text: "A" }, 0)
    s = applyAskEvent(s, { type: "answer_delta", text: "B" }, 1)
    // replay of index 0 and 1 must NOT double-append
    s = applyAskEvent(s, { type: "answer_delta", text: "A" }, 0)
    s = applyAskEvent(s, { type: "answer_delta", text: "B" }, 1)
    expect(s.answer).toBe("AB")
  })

  it("adopts the authoritative answer event (replace, not append)", () => {
    const s = feed([
      { type: "answer_delta", text: "draft" },
      {
        type: "answer", answer: "**Assuming X.**\n\nfinal [1]", refusal: false,
        citations: [{ n: 1, book: "B", chapter: "", page: 2, location: "B, p.2" }], figures: [],
      },
    ])
    expect(s.answer).toBe("**Assuming X.**\n\nfinal [1]")
    expect(s.sources[0].page).toBe(2)
    expect(s.status).toBe("answer")
  })

  it("clears sources/figures on a refusal answer", () => {
    const s = feed([
      { type: "sources", citations: [{ n: 1, book: "B", chapter: "", page: 1, location: "B, p.1" }] },
      { type: "answer", answer: "Not found in the provided sources.", refusal: true, citations: [], figures: [] },
    ])
    expect(s.sources).toEqual([])
  })

  it("marks done", () => {
    const s = feed([{ type: "done" }])
    expect(s.done).toBe(true)
  })

  it("reduces evidence + decision events into state", () => {
    const s = feed([
      { type: "answer", answer: "It is indicated [1].", refusal: false, citations: [], figures: [] },
      {
        type: "evidence",
        evidence_spans: [{ claim: "It is indicated [1].", marker: "1", quote: "q", matched: true, score: 1 }],
      },
      {
        type: "decision",
        decision_card: {
          prose: "It is indicated [1].",
          bottom_line: [{ text: "It is indicated.", markers: ["1"], category: "indication",
                          quote: "q", span_matched: true, status: "settled", flags: [], year: null }],
          decision_furniture: [],
          uncertainties: [],
          coverage_gaps: ["did not address: beta"],
          conflicts: [],
        },
      },
    ])
    expect(s.evidenceSpans[0].matched).toBe(true)
    expect(s.decisionCard?.bottom_line[0].category).toBe("indication")
    expect(s.decisionCard?.coverage_gaps).toEqual(["did not address: beta"])
  })
})

describe("store round-trip", () => {
  it("saves and loads", () => {
    const mem: Record<string, string> = {}
    const storage = {
      getItem: (k: string) => mem[k] ?? null,
      setItem: (k: string, v: string) => {
        mem[k] = v
      },
    }
    const s = feed([{ type: "answer_delta", text: "hi" }])
    saveAsk(storage, s)
    expect(loadAsk(storage)?.answer).toBe("hi")
  })
})
