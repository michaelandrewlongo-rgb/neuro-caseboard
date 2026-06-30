import { describe, it, expect, vi, afterEach } from "vitest"
import { startAsk } from "./api"

function mockFetch(res: { ok: boolean; status: number; body: unknown }) {
  return vi.fn().mockResolvedValue({
    ok: res.ok,
    status: res.status,
    json: () => Promise.resolve(res.body),
  })
}

afterEach(() => vi.unstubAllGlobals())

describe("startAsk validates the job-start response", () => {
  it("returns the job_id on a successful start", async () => {
    vi.stubGlobal("fetch", mockFetch({ ok: true, status: 200, body: { job_id: "abc123" } }))
    expect(await startAsk("q")).toEqual({ job_id: "abc123" })
  })

  it("throws on a non-ok response so the caller shows a visible error (not a silent hang)", async () => {
    // Previously the error body was consumed as {job_id: undefined} and a stream opened to
    // /stream/undefined, hanging forever with no visible failure (baseline A6).
    vi.stubGlobal("fetch", mockFetch({
      ok: false, status: 422, body: { kind: "error", error: "empty question" },
    }))
    await expect(startAsk("")).rejects.toThrow(/empty question/)
  })

  it("throws when the response body carries no job_id", async () => {
    vi.stubGlobal("fetch", mockFetch({ ok: true, status: 200, body: {} }))
    await expect(startAsk("q")).rejects.toThrow()
  })
})
