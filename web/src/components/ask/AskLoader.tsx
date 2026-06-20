import { useEffect, useState } from "react"
import BlurText from "@/components/BlurText"
import { cn } from "@/lib/utils"

const STEPS = [
  "Searching your textbook corpus…",
  "Ranking the most relevant passages…",
  "Synthesizing a cited answer · Vertex…",
  "Scanning recent PubMed literature…",
]

/** Slow-call loader: glass panel with a crimson mono eyebrow, pulsing dot, and a BlurText
    status line (animation in the chrome) cycling real pipeline stages, plus shimmer placeholders. */
export default function AskLoader() {
  const [i, setI] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setI((p) => (p + 1) % STEPS.length), 3200)
    return () => clearInterval(t)
  }, [])

  return (
    <div
      className="surface p-6"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      {/* Crimson mono eyebrow (Ask surface = crimson accent) */}
      <p
        className="mb-3 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
        style={{ color: "#6b93ff" }}
        aria-hidden
      >
        Ask · Corpus Retrieval
      </p>

      <div className="flex items-center gap-3">
        {/* Pulsing crimson status dot — pulse keyframe in index.css, guarded by reduced-motion */}
        <span
          className="inline-block h-2 w-2 shrink-0 rounded-full"
          style={{
            background: "#6b93ff",
            boxShadow: "0 0 8px rgba(107,147,255,.7)",
            animation: "pulse 2.4s ease-in-out infinite",
          }}
          aria-hidden
        />
        <div aria-hidden className="min-w-0">
          <BlurText
            key={i}
            text={STEPS[i]}
            animateBy="words"
            delay={40}
            className="font-mono text-sm text-foreground"
          />
        </div>
        {/* Stable, non-animated text the screen reader actually announces (the cycling stages above
            are decorative). */}
        <span className="sr-only">
          Working on your answer — searching the corpus, synthesizing a cited answer, and scanning
          recent literature. This usually takes 30–80 seconds.
        </span>
      </div>

      {/* Shimmer bars — animate-pulse is disabled under prefers-reduced-motion in index.css */}
      <div className="mt-6 flex flex-col gap-3" aria-hidden>
        {["w-11/12", "w-full", "w-10/12", "w-9/12", "w-full", "w-7/12"].map((w, idx) => (
          <div
            key={idx}
            className={cn("h-3 animate-pulse rounded-lg", w)}
            style={{ background: "rgba(255,255,255,.06)" }}
          />
        ))}
      </div>

      <p className="mt-5 font-mono text-xs text-muted-foreground" aria-hidden>
        Usually 30–80 seconds — retrieval, citation-grounded synthesis, and a live literature lookup.
      </p>
    </div>
  )
}
