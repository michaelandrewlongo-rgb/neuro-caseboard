/**
 * Spaced-repetition scheduler (BACKLOG P4 #13) — an SM-2-lite algorithm.
 *
 * Pure and clock-injectable so the schedule maths is unit-testable. Given a card's prior schedule
 * and a self-rating, it returns the next schedule (ease, interval, due time). Drives self-rating,
 * spaced repetition, missed-card review (lapses), and progress tracking.
 */
export type Rating = "again" | "hard" | "good" | "easy"

export interface CardSchedule {
  ease: number // ease factor (>= 1.3); starts at 2.5
  intervalDays: number // current inter-review interval in days
  reps: number // consecutive successful reviews
  due: number // epoch ms when the card is next due
  lapses: number // times rated "again" after first learning
}

const DAY = 86_400_000
const MIN_EASE = 1.3
const AGAIN_DELAY = 10 * 60_000 // 10 minutes

const round2 = (n: number) => Math.round(n * 100) / 100

export function newSchedule(now: number): CardSchedule {
  return { ease: 2.5, intervalDays: 0, reps: 0, due: now, lapses: 0 }
}

export function schedule(s: CardSchedule, rating: Rating, now: number): CardSchedule {
  const { lapses } = s
  let { ease, intervalDays, reps } = s

  if (rating === "again") {
    return {
      ease: round2(Math.max(MIN_EASE, ease - 0.2)),
      intervalDays: 0,
      reps: 0,
      lapses: lapses + 1,
      due: now + AGAIN_DELAY,
    }
  }

  if (rating === "hard") ease = Math.max(MIN_EASE, ease - 0.15)
  else if (rating === "easy") ease = ease + 0.15

  reps += 1
  if (reps === 1) intervalDays = rating === "easy" ? 4 : 1
  else if (reps === 2) intervalDays = 6
  else {
    const factor = rating === "hard" ? 1.2 : ease
    const easyBonus = rating === "easy" ? 1.3 : 1
    intervalDays = Math.round(intervalDays * factor * easyBonus)
  }
  intervalDays = Math.max(1, intervalDays)

  return { ease: round2(ease), intervalDays, reps, lapses, due: now + intervalDays * DAY }
}

export function isDue(s: CardSchedule, now: number): boolean {
  return now >= s.due
}
