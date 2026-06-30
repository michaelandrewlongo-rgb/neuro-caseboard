// Persistent mirror of an in-flight / completed Ask response. The server owns the truth (a
// replayable event log); this is a local cache so a refresh/tab-change restores instantly and a
// reconnect resumes from `nextIndex`. Dedup is by event index — events already applied are ignored.
import type { Citation, Figure, Literature, Variant } from "./api"

export interface Verification {
  n_cited_claims: number
  n_unsupported: number
  groundedness: number
  unsupported_markers: string[]
}

export type AskEvent =
  | { type: "sources"; citations: Citation[] }
  | { type: "figures"; figures: Figure[] }
  | { type: "answer_delta"; text: string }
  | { type: "answer"; answer: string; refusal: boolean; citations: Citation[]; figures: Figure[] }
  | { type: "literature"; literature: Literature | null }
  | { type: "verification"; verification: Verification | null }
  | { type: "clarification"; question: string; variants: Variant[] }
  | { type: "unavailable"; reason: string }
  | { type: "error"; error: string }
  | { type: "done" }

export type AskStatus = "streaming" | "answer" | "clarification" | "unavailable" | "error"

export interface AskState {
  question: string
  jobId: string
  status: AskStatus
  answer: string
  sources: Citation[]
  figures: Figure[]
  literature: Literature | null
  verification: Verification | null
  variants: Variant[]
  reason: string // unavailable/error message
  nextIndex: number // next un-applied event index (the reconnect cursor)
  done: boolean
}

export function emptyAskState(question: string, jobId: string): AskState {
  return {
    question, jobId, status: "streaming", answer: "", sources: [], figures: [],
    literature: null, verification: null, variants: [], reason: "", nextIndex: 0, done: false,
  }
}

export function applyAskEvent(state: AskState, ev: AskEvent, index: number): AskState {
  if (index < state.nextIndex) return state // already applied — dedup on replay
  const s: AskState = { ...state, nextIndex: index + 1 }
  switch (ev.type) {
    case "sources":
      s.sources = ev.citations
      break
    case "figures":
      s.figures = ev.figures
      break
    case "answer_delta":
      s.answer = state.answer + ev.text
      break
    case "answer":
      s.answer = ev.answer
      s.status = "answer"
      s.sources = ev.refusal ? [] : ev.citations
      s.figures = ev.refusal ? [] : ev.figures
      break
    case "literature":
      s.literature = ev.literature
      break
    case "verification":
      s.verification = ev.verification
      break
    case "clarification":
      s.status = "clarification"
      s.variants = ev.variants
      break
    case "unavailable":
      s.status = "unavailable"
      s.reason = ev.reason
      break
    case "error":
      s.status = "error"
      s.reason = ev.error
      break
    case "done":
      s.done = true
      break
  }
  return s
}

const KEY = "neuro.ask.v1"

export function loadAsk(storage: { getItem(k: string): string | null }): AskState | null {
  try {
    return JSON.parse(storage.getItem(KEY) ?? "null") as AskState | null
  } catch {
    return null
  }
}

export function saveAsk(storage: { setItem(k: string, v: string): void }, state: AskState): void {
  storage.setItem(KEY, JSON.stringify(state))
}

export function clearAsk(storage: { setItem(k: string, v: string): void }): void {
  storage.setItem(KEY, "null")
}
