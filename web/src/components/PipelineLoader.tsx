import { useEffect, useState } from "react"
import BlurText from "@/components/BlurText"
import { Card } from "@/components/ui"

/** Generic slow-call loader: a react-bits BlurText status line cycling real pipeline stages plus
    shimmer placeholders. Animation lives in the chrome, never in clinical content. */
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
    <Card className="p-6" role="status" aria-live="polite" aria-busy="true">
      <div className="flex items-center gap-3">
        <span className="h-2 w-2 animate-pulse rounded-full bg-primary" aria-hidden />
        <div aria-hidden className="min-w-0">
          <BlurText
            key={i}
            text={steps[i]}
            animateBy="words"
            delay={40}
            className="font-mono text-sm text-primary-ink"
          />
        </div>
        {/* Stable, non-animated text the screen reader announces (the cycling stages are decorative). */}
        <span className="sr-only">Working on your request. {estimate}</span>
      </div>
      <div className="mt-6 flex flex-col gap-3" aria-hidden>
        {Array.from({ length: bars }).map((_, idx) => (
          <div
            key={idx}
            className={`h-3 animate-pulse rounded bg-muted ${
              ["w-11/12", "w-full", "w-10/12", "w-9/12", "w-full", "w-7/12", "w-8/12"][idx % 7]
            }`}
          />
        ))}
      </div>
      <p className="mt-5 font-mono text-xs text-muted-foreground" aria-hidden>{estimate}</p>
    </Card>
  )
}
