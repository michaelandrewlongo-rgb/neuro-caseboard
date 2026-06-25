import { useRef, useState } from "react"
import type { BriefingFigureView } from "@/lib/api"

// High-yield figure gallery: a BOUNDED scroll region (spec §10), responsive via Tailwind `sm:`
// classes — never inline gridTemplateColumns (web/ has no useMediaQuery; inline grid clips on
// mobile). Full-size view reuses the native <dialog> + showModal() lightbox idiom (PR #60).
export default function BriefingFigureGallery({ figures }: { figures: BriefingFigureView[] }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [active, setActive] = useState<BriefingFigureView | null>(null)
  if (!figures.length) return null

  const open = (f: BriefingFigureView) => {
    if (!f.image_available) return
    setActive(f)
    dialogRef.current?.showModal()
  }

  return (
    <section className="flex flex-col gap-3">
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-secondary">
        High-yield figures · {figures.length}
      </p>
      <div className="max-h-[28rem] overflow-y-auto rounded-2xl border border-border bg-card p-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {figures.map((f) => (
            <figure key={f.fig_id} className="overflow-hidden rounded-xl border border-border bg-muted">
              {f.image_available ? (
                <button
                  type="button"
                  onClick={() => open(f)}
                  className="block w-full cursor-zoom-in appearance-none border-0 bg-background p-0"
                  aria-label={`Enlarge ${f.fig_id}`}
                >
                  <img src={f.image_url ?? ""} alt={f.caption ?? f.fig_id} className="max-h-56 w-full object-contain" />
                </button>
              ) : (
                <div className="flex h-32 items-center justify-center bg-background text-xs text-muted-foreground">
                  image unavailable
                </div>
              )}
              <figcaption className="p-3 text-xs leading-relaxed text-muted-foreground">
                <span className="font-mono font-bold text-secondary">{f.fig_id}</span> {f.caption}
                {f.citation && <span className="mt-1 block text-[11px] text-muted-foreground/80">{f.citation}</span>}
              </figcaption>
            </figure>
          ))}
        </div>
      </div>

      <dialog
        ref={dialogRef}
        onClick={(e) => {
          // Clicking the ::backdrop has target === the dialog element; inner content won't match.
          if (e.target === dialogRef.current) dialogRef.current?.close()
        }}
        className="m-auto max-w-3xl rounded-xl bg-card p-0 text-foreground backdrop:bg-black/70"
      >
        {active && (
          <div className="flex flex-col">
            <img src={active.image_url ?? ""} alt={active.caption ?? active.fig_id} className="max-h-[70vh] w-full object-contain" />
            <div className="p-4">
              <p className="text-sm text-foreground">
                <span className="font-mono font-bold text-secondary">{active.fig_id}</span> {active.caption}
              </p>
              {active.citation && <p className="mt-1 text-xs text-muted-foreground">{active.citation}</p>}
              <button
                type="button"
                onClick={() => dialogRef.current?.close()}
                className="mt-3 rounded-md border border-border px-3 py-1 font-mono text-xs text-muted-foreground"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </dialog>
    </section>
  )
}
