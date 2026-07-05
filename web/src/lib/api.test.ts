// web/src/lib/api.test.ts
import { describe, expect, it, vi, beforeEach } from "vitest"
import { askQuestion, startAsk } from "./api"

describe("Ask request bodies", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(() =>
      Promise.resolve({ json: () => Promise.resolve({ kind: "answer" }) } as Response)))
  })

  it("askQuestion omits cerebrovascular by default", async () => {
    await askQuestion("q")
    const [, init] = (fetch as unknown as vi.Mock).mock.calls[0]
    const body = JSON.parse(init.body as string)
    expect(body.cerebrovascular).toBe(false)
  })

  it("askQuestion sends cerebrovascular=true when passed", async () => {
    await askQuestion("q", undefined, false, true)
    const [, init] = (fetch as unknown as vi.Mock).mock.calls[0]
    const body = JSON.parse(init.body as string)
    expect(body.cerebrovascular).toBe(true)
  })

  it("startAsk sends cerebrovascular=true when passed", async () => {
    vi.stubGlobal("fetch", vi.fn(() =>
      Promise.resolve({ json: () => Promise.resolve({ job_id: "abc" }) } as Response)))
    await startAsk("q", false, true)
    const [, init] = (fetch as unknown as vi.Mock).mock.calls[0]
    const body = JSON.parse(init.body as string)
    expect(body.cerebrovascular).toBe(true)
  })
})
