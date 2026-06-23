import { useEffect, useState } from "react"
import StepChecklist from "@/components/StepChecklist"
import { advanceStep } from "@/lib/loaderSteps"
import { cn } from "@/lib/utils"

/** Generic slow-call loader: glass panel with a mono eyebrow and a persistent,
    MONOTONIC step checklist (advances by clamp, never wraps back) plus shimmer
    placeholders. Animation lives in the chrome, never in clinical content. */
export default function PipelineLoader({
  steps,
  estimate,
  bars = 6,
  eyebrow = "Processing · Pipeline",
  srText,
}: {
  steps: string[]
  estimate: string
  bars?: number
  eyebrow?: string
  srText?: string
}) {
  const [i, setI] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setI((p) => advanceStep(p, steps.length)), 3200)
    return () => clearInterval(t)
  }, [steps.length])

  return (
    <div
      className="surface p-6"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      {/* Mono eyebrow */}
      <p
        className="mb-4 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
        style={{ color: "#6b93ff" }}
        aria-hidden
      >
        {eyebrow}
      </p>

      {/* Persistent monotonic checklist (static labels → never blank) */}
      <StepChecklist steps={steps} current={i} />

      {/* Stable, non-animated text the screen reader announces (the checklist is decorative). */}
      <span className="sr-only">{srText ?? `Working on your request. ${estimate}`}</span>

      {/* Shimmer bars — animate-pulse is disabled under prefers-reduced-motion in index.css */}
      <div className="mt-6 flex flex-col gap-3" aria-hidden>
        {Array.from({ length: bars }).map((_, idx) => (
          <div
            key={idx}
            className={cn(
              "h-3 animate-pulse rounded-lg",
              ["w-11/12", "w-full", "w-10/12", "w-9/12", "w-full", "w-7/12", "w-8/12"][idx % 7],
            )}
            style={{ background: "rgba(255,255,255,.06)" }}
          />
        ))}
      </div>

      <p className="mt-5 font-mono text-xs text-muted-foreground" aria-hidden>
        {estimate}
      </p>
    </div>
  )
}
