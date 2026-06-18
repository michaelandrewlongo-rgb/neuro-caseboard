import { useState } from "react"
import type { Figure } from "@/lib/api"
import { Card } from "@/components/ui"

function FigureCard({ fig }: { fig: Figure }) {
  const [failed, setFailed] = useState(false)
  const showImg = fig.image_url && fig.image_available && !failed
  return (
    <Card hover className="overflow-hidden">
      <div className="flex aspect-[4/3] items-center justify-center bg-background">
        {showImg ? (
          <img
            src={fig.image_url!}
            alt={fig.caption || fig.location}
            loading="lazy"
            onError={() => setFailed(true)}
            className="h-full w-full object-contain"
          />
        ) : (
          <span className="px-4 text-center font-mono text-xs text-muted-foreground">
            image unavailable
          </span>
        )}
      </div>
      <figcaption className="space-y-1 p-3.5">
        <span className="font-mono text-[10px] uppercase tracking-wider text-primary">
          [{fig.source_n}] {fig.location}
        </span>
        {fig.caption && <p className="text-xs leading-snug text-muted-foreground">{fig.caption}</p>}
      </figcaption>
    </Card>
  )
}

export default function FigureGrid({ figures }: { figures: Figure[] }) {
  if (!figures.length) return null
  return (
    <section>
      <h2 className="eyebrow mb-3">Figures</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {figures.map((f, i) => (
          <FigureCard key={`${f.source_n}-${i}`} fig={f} />
        ))}
      </div>
    </section>
  )
}
