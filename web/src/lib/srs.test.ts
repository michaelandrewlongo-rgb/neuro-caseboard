import { describe, it, expect } from "vitest"
import { newSchedule, schedule, isDue } from "./srs"
import {
  rate,
  dueCardIds,
  missedCardIds,
  progress,
  loadReview,
  type KVStorage,
} from "./reviewStore"

const T0 = 1_700_000_000_000
const DAY = 86_400_000

describe("srs scheduler (BACKLOG P4 #13)", () => {
  it("a new card is due immediately", () => {
    const s = newSchedule(T0)
    expect(isDue(s, T0)).toBe(true)
    expect(s.reps).toBe(0)
  })

  it("'good' grows the interval across reps", () => {
    let s = schedule(newSchedule(T0), "good", T0)
    expect(s.intervalDays).toBe(1)
    s = schedule(s, "good", T0)
    expect(s.intervalDays).toBe(6)
    s = schedule(s, "good", T0)
    expect(s.intervalDays).toBeGreaterThan(6) // interval * ease
    expect(s.due).toBe(T0 + s.intervalDays * DAY)
  })

  it("'again' resets reps, records a lapse, lowers ease, and is due in ~10 min", () => {
    let s = schedule(newSchedule(T0), "good", T0)
    s = schedule(s, "again", T0)
    expect(s.reps).toBe(0)
    expect(s.lapses).toBe(1)
    expect(s.ease).toBeLessThan(2.5)
    expect(s.due).toBe(T0 + 10 * 60_000)
  })

  it("'easy' advances faster than 'good', and ease never drops below 1.3", () => {
    const easy = schedule(newSchedule(T0), "easy", T0)
    const good = schedule(newSchedule(T0), "good", T0)
    expect(easy.intervalDays).toBeGreaterThan(good.intervalDays)
    let s = newSchedule(T0)
    for (let i = 0; i < 10; i++) s = schedule(s, "hard", T0) // hammer ease down
    expect(s.ease).toBeGreaterThanOrEqual(1.3)
  })
})

function memStorage(): KVStorage {
  const m = new Map<string, string>()
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => void m.set(k, v) }
}

describe("review store (BACKLOG P4 #13)", () => {
  it("rating persists and the same card is no longer due until its interval elapses", () => {
    const st = memStorage()
    rate(st, "c1", "good", T0)
    expect(dueCardIds(st, ["c1", "c2"], T0)).toEqual(["c2"]) // c1 scheduled, c2 new
    expect(dueCardIds(st, ["c1"], T0 + 2 * DAY)).toEqual(["c1"]) // due again later
  })

  it("missed cards are those with a lapse", () => {
    const st = memStorage()
    rate(st, "c1", "good", T0)
    rate(st, "c2", "good", T0)
    rate(st, "c2", "again", T0)
    expect(missedCardIds(st)).toEqual(["c2"])
  })

  it("progress counts reviewed/mature/lapses", () => {
    const st = memStorage()
    rate(st, "c1", "good", T0)
    rate(st, "c1", "again", T0)
    const p = progress(st)
    expect(p.reviewed).toBe(1)
    expect(p.lapses).toBe(1)
    expect(loadReview(st)["c1"]).toBeDefined()
  })
})
