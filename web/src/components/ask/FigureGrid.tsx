import { useState } from "react"
import type { Figure } from "@/lib/api"

function FigureCard({ fig }: { fig: Figure }) {
  const [failed, setFailed] = useState(false)
  const showImg = fig.image_url && fig.image_available && !failed

  return (
    <figure className="overflow-hidden rounded-lg border border-navy-700/60 bg-navy-900/50">
      <div className="flex aspect-[4/3] items-center justify-center bg-navy-950/60">
        {showImg ? (
          <img
            src={fig.image_url!}
            alt={fig.caption || fig.location}
            loading="lazy"
            onError={() => setFailed(true)}
            className="h-full w-full object-contain"
          />
        ) : (
          <span className="px-4 text-center font-mono text-xs text-ink-faint">
            image unavailable
          </span>
        )}
      </div>
      <figcaption className="space-y-1 p-3">
        <span className="font-mono text-[10px] uppercase tracking-wider text-teal">
          [{fig.source_n}] {fig.location}
        </span>
        {fig.caption && <p className="text-xs leading-snug text-ink-dim">{fig.caption}</p>}
      </figcaption>
    </figure>
  )
}

export default function FigureGrid({ figures }: { figures: Figure[] }) {
  if (!figures.length) return null
  return (
    <section>
      <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-ink-faint">Figures</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {figures.map((f, i) => (
          <FigureCard key={`${f.source_n}-${i}`} fig={f} />
        ))}
      </div>
    </section>
  )
}
