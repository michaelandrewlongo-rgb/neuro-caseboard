/**
 * Persistent review store for Cards study mode (BACKLOG P4 #13).
 *
 * Wraps the spaced-repetition scheduler with persistence over a minimal key/value `Storage`
 * (localStorage in the app, an in-memory fake in tests). Provides self-rating, the due/new review
 * queue, missed-card review, and progress stats. All logic is pure given the injected storage+clock.
 */
import { type CardSchedule, type Rating, newSchedule, schedule, isDue } from "./srs"

export interface KVStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

const KEY = "neuro.cards.review.v1"
const MATURE_DAYS = 21

export type ReviewState = Record<string, CardSchedule>

export function loadReview(storage: KVStorage): ReviewState {
  try {
    return JSON.parse(storage.getItem(KEY) ?? "{}") as ReviewState
  } catch {
    return {}
  }
}

export function saveReview(storage: KVStorage, state: ReviewState): void {
  storage.setItem(KEY, JSON.stringify(state))
}

/** Record a self-rating for a card and persist the new schedule. Returns the updated state. */
export function rate(storage: KVStorage, cardId: string, rating: Rating, now: number): ReviewState {
  const state = loadReview(storage)
  const current = state[cardId] ?? newSchedule(now)
  state[cardId] = schedule(current, rating, now)
  saveReview(storage, state)
  return state
}

/** The review queue: cards never seen (new) or whose schedule is due, preserving input order. */
export function dueCardIds(storage: KVStorage, cardIds: string[], now: number): string[] {
  const state = loadReview(storage)
  return cardIds.filter((id) => {
    const s = state[id]
    return !s || isDue(s, now)
  })
}

/** Missed cards: those with at least one lapse (rated "again" after learning) — for focused review. */
export function missedCardIds(storage: KVStorage): string[] {
  const state = loadReview(storage)
  return Object.keys(state).filter((id) => state[id].lapses > 0)
}

export function progress(storage: KVStorage): {
  reviewed: number
  mature: number
  lapses: number
} {
  const vals = Object.values(loadReview(storage))
  return {
    reviewed: vals.length,
    mature: vals.filter((s) => s.intervalDays >= MATURE_DAYS).length,
    lapses: vals.reduce((sum, s) => sum + s.lapses, 0),
  }
}
