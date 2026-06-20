import { useEffect, useState } from "react"
import BlurText from "@/components/BlurText"
import { cn } from "@/lib/utils"

/** Generic slow-call loader: glass panel with a mono eyebrow, pulsing crimson dot, and a
    BlurText status line cycling real pipeline stages plus shimmer placeholders.
    Animation lives in the chrome, never in clinical content. */
export default function PipelineLoader({
  steps,
  estimate,
  bars = 6,
}: {
  steps: string[]
  estimate: string
  bars?: number
}) {
  const [i, setI] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setI((p) => (p + 1) % steps.length), 3200)
    return () => clearInterval(t)
  }, [steps.length])

  return (
    <div
      className="surface p-6"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      {/* Teal mono eyebrow */}
      <p
        className="mb-3 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
        style={{ color: "#6fc0b8" }}
        aria-hidden
      >
        Processing · Pipeline
      </p>

      <div className="flex items-center gap-3">
        {/* Pulsing crimson status dot — pulse keyframe in index.css, guarded by reduced-motion */}
        <span
          className="inline-block h-2 w-2 shrink-0 rounded-full"
          style={{
            background: "#d8413a",
            boxShadow: "0 0 8px rgba(216,65,58,.7)",
            animation: "pulse 2.4s ease-in-out infinite",
          }}
          aria-hidden
        />
        <div aria-hidden className="min-w-0">
          <BlurText
            key={i}
            text={steps[i]}
            animateBy="words"
            delay={40}
            className="font-mono text-sm text-foreground"
          />
        </div>
        {/* Stable, non-animated text the screen reader announces (the cycling stages are decorative). */}
        <span className="sr-only">Working on your request. {estimate}</span>
      </div>

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
