import { useEffect, useState } from "react"
import BlurText from "@/components/BlurText"
import { Card } from "@/components/ui"

const STEPS = [
  "Searching your textbook corpus…",
  "Ranking the most relevant passages…",
  "Synthesizing a cited answer · Vertex…",
  "Scanning recent PubMed literature…",
]

/** Slow-call loader: a react-bits BlurText status line (animation in the chrome) cycling real
    pipeline stages, plus shimmer placeholders. */
export default function AskLoader() {
  const [i, setI] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setI((p) => (p + 1) % STEPS.length), 3200)
    return () => clearInterval(t)
  }, [])

  return (
    <Card className="p-6">
      <div className="flex items-center gap-3">
        <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
        <BlurText
          key={i}
          text={STEPS[i]}
          animateBy="words"
          delay={40}
          className="font-mono text-sm text-primary"
        />
      </div>
      <div className="mt-6 flex flex-col gap-3" aria-hidden>
        {["w-11/12", "w-full", "w-10/12", "w-9/12", "w-full", "w-7/12"].map((w, idx) => (
          <div key={idx} className={`h-3 ${w} animate-pulse rounded bg-muted`} />
        ))}
      </div>
      <p className="mt-5 font-mono text-xs text-muted-foreground">
        Usually 30–80 seconds — retrieval, citation-grounded synthesis, and a live literature lookup.
      </p>
    </Card>
  )
}
