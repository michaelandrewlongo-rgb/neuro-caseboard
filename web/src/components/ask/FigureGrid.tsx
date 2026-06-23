import { useRef, useState } from "react"
import type { Figure } from "@/lib/api"
import { figureIsEnlargeable } from "@/lib/figures"

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

function FigureCard({ fig, onEnlarge }: { fig: Figure; onEnlarge?: (fig: Figure) => void }) {
  const [failed, setFailed] = useState(false)
  const showImg = Boolean(fig.image_url) && fig.image_available && !failed
  // The showImg condition already implies image_url + image_available, but use the helper so
  // the "only real images enlarge" intent is explicit (and unit-tested).
  const canEnlarge = showImg && figureIsEnlargeable(fig)
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
        <button
          type="button"
          onClick={() => {
            if (canEnlarge) onEnlarge?.(fig)
          }}
          aria-label={`Enlarge figure ${fig.source_n ?? ""}`.trim()}
          className="group relative flex aspect-[4/3] w-full appearance-none items-center justify-center overflow-hidden border-0 bg-background p-0 cursor-zoom-in"
        >
          <img
            src={fig.image_url!}
            alt={fig.caption || fig.location}
            loading="lazy"
            onError={() => setFailed(true)}
            className="h-full w-full object-contain"
          />
          <span
            className="pointer-events-none absolute right-2 top-2 rounded-[6px] px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.18em] opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100"
            style={{ background: "rgba(0,0,0,.65)", color: "#6b93ff" }}
          >
            ⤢ Enlarge
          </span>
        </button>
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
  const [selected, setSelected] = useState<Figure | null>(null)
  const dialogRef = useRef<HTMLDialogElement>(null)

  function enlarge(fig: Figure) {
    setSelected(fig)
    dialogRef.current?.showModal()
    document.body.style.overflow = "hidden"
  }

  if (!figures.length) return null
  return (
    <section>
      <h2 className="eyebrow mb-3">Figures</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {figures.map((f, i) => (
          <FigureCard key={`${f.source_n ?? "f"}-${i}`} fig={f} onEnlarge={enlarge} />
        ))}
      </div>

      {/* One shared lightbox. Native <dialog> + showModal() gives backdrop, ESC, focus-trap,
          and aria-modal for free. ESC fires `close` → onClose clears `selected`. */}
      <dialog
        ref={dialogRef}
        onClose={() => {
          setSelected(null)
          document.body.style.overflow = ""
        }}
        onClick={(e) => {
          // Clicking the ::backdrop has target === the dialog element; inner content won't match.
          if (e.target === dialogRef.current) dialogRef.current?.close()
        }}
        className="m-auto max-h-[90vh] max-w-[92vw] backdrop:bg-black/80"
        style={{
          background: "#0c0d10",
          border: "1px solid rgba(255,255,255,.1)",
          borderRadius: "var(--radius-lg)",
          color: "var(--color-foreground, #e7e9ee)",
        }}
      >
        {selected && (
          <div className="flex flex-col gap-3 p-4">
            <div className="flex items-start justify-between gap-4">
              <span
                className="font-mono text-[10px] uppercase tracking-wider"
                style={{ color: "#6b93ff" }}
              >
                [{selected.source_n}] {selected.location}
              </span>
              <button
                type="button"
                onClick={() => dialogRef.current?.close()}
                aria-label="Close enlarged figure"
                className="flex h-7 w-7 shrink-0 appearance-none items-center justify-center rounded-full border-0 text-lg leading-none cursor-pointer"
                style={{ background: "rgba(255,255,255,.08)", color: "#e7e9ee" }}
              >
                ×
              </button>
            </div>
            <img
              src={selected.image_url ?? undefined}
              alt={selected.caption || selected.location}
              className="max-h-[85vh] max-w-[90vw] object-contain"
            />
            {selected.caption && (
              <p className="max-w-[90vw] text-xs leading-snug text-muted-foreground">
                {selected.caption}
              </p>
            )}
          </div>
        )}
      </dialog>
    </section>
  )
}
