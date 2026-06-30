import { describe, it, expect } from "vitest"
import {
  applyAskEvent, emptyAskState, loadAsk, saveAsk, streamErrorState, type AskEvent,
} from "./askStore"

describe("streamErrorState (fatal EventSource error → visible degraded state)", () => {
  it("turns a CLOSED (fatal, e.g. 404 expired job) error mid-stream into a visible unavailable state", () => {
    const streaming = emptyAskState("q", "job1") // status:"streaming", done:false
    const next = streamErrorState(streaming, 2 /* EventSource.CLOSED */)
    expect(next).not.toBeNull()
    expect(next!.status).toBe("unavailable")
    expect(next!.done).toBe(true) // terminal, so a remount won't retry the dead job
    expect(next!.reason).toMatch(/connection lost|expired/i)
  })
  it("ignores a transient (CONNECTING) error — the browser auto-reconnects", () => {
    expect(streamErrorState(emptyAskState("q", "job1"), 0 /* CONNECTING */)).toBeNull()
  })
  it("does nothing once the stream is already terminal (done/answer)", () => {
    const done = { ...emptyAskState("q", "job1"), done: true, status: "answer" as const }
    expect(streamErrorState(done, 2)).toBeNull()
  })
  it("does nothing with no state", () => {
    expect(streamErrorState(null, 2)).toBeNull()
  })
})

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
