/**
 * loaderSteps — pure step-state helpers for the slow-call loaders.
 *
 * The backend Ask/Build call is a single request with no per-stage progress
 * events, so the loader checklist is a *timed* approximation, not telemetry.
 * It is HONEST regardless: it advances monotonically (clamp, never wrap), never
 * marks a later stage done before an earlier one, and holds on the final stage
 * until the response actually arrives. Kept here (no React import) so it stays
 * unit-testable and doesn't trip react-refresh/only-export-components.
 */

export type StepState = "done" | "active" | "pending"

/** Advance one step, clamped to the last index — never wraps back to 0 (monotonic progress). */
export function advanceStep(current: number, total: number): number {
  return Math.min(current + 1, Math.max(0, total - 1))
}

/** Per-step state for a checklist: indices before `current` are done, `current` is active, after are pending. */
export function stepStates(total: number, current: number): StepState[] {
  return Array.from({ length: total }, (_, i) =>
    i < current ? "done" : i === current ? "active" : "pending",
  )
}

/** Format an elapsed-seconds count as M:SS for the live loader stopwatch (e.g. 83 -> "1:23").
    Floors fractional seconds and clamps negatives to "0:00". */
export function formatElapsed(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds))
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}:${r.toString().padStart(2, "0")}`
}
