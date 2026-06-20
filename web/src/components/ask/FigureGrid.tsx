import { useState } from "react"
import type { Figure } from "@/lib/api"

// Dashed hatch placeholder — shown when image_available is false or image load fails.
function FigurePlaceholder({ fig }: { fig: Figure }) {
  return (
    <div
      className="flex aspect-[4/3] flex-col items-center justify-center gap-3"
      style={{
        background:
          "repeating-linear-gradient(45deg, rgba(255,255,255,.03), rgba(255,255,255,.03) 1px, transparent 1px, transparent 10px)",
        border: "1px dashed rgba(255,255,255,.14)",
        borderRadius: "var(--radius-md)",
      }}
    >
      <span
        className="rounded-[6px] px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
        style={{ background: "rgba(107,147,255,.15)", color: "#6b93ff" }}
      >
        FIG {fig.source_n ?? "—"}
      </span>
      {fig.caption && (
        <p
          className="max-w-[82%] text-center font-mono text-[9px] uppercase leading-relaxed tracking-wider text-muted-foreground"
        >
          {fig.caption}
        </p>
      )}
    </div>
  )
}

function FigureCard({ fig }: { fig: Figure }) {
  const [failed, setFailed] = useState(false)
  const showImg = Boolean(fig.image_url) && fig.image_available && !failed
  return (
    <figure
      className="overflow-hidden"
      style={{
        background: "rgba(255,255,255,.022)",
        border: "1px solid rgba(255,255,255,.08)",
        borderRadius: "var(--radius-lg)",
      }}
    >
      {showImg ? (
        <div className="flex aspect-[4/3] items-center justify-center overflow-hidden bg-background">
          <img
            src={fig.image_url!}
            alt={fig.caption || fig.location}
            loading="lazy"
            onError={() => setFailed(true)}
            className="h-full w-full object-contain"
          />
        </div>
      ) : (
        <div className="p-3">
          <FigurePlaceholder fig={fig} />
        </div>
      )}
      <figcaption className="space-y-1 px-3.5 pb-3.5 pt-2">
        <span
          className="font-mono text-[10px] uppercase tracking-wider"
          style={{ color: "#6b93ff" }}
        >
          [{fig.source_n}] {fig.location}
        </span>
        {fig.caption && showImg && (
          <p className="text-xs leading-snug text-muted-foreground">{fig.caption}</p>
        )}
      </figcaption>
    </figure>
  )
}

export default function FigureGrid({ figures }: { figures: Figure[] }) {
  if (!figures.length) return null
  return (
    <section>
      <h2 className="eyebrow mb-3">Figures</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {figures.map((f, i) => (
          <FigureCard key={`${f.source_n ?? "f"}-${i}`} fig={f} />
        ))}
      </div>
    </section>
  )
}
