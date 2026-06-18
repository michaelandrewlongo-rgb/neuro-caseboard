import type { Dossier, DossierClaim, DossierFigure, DossierSection } from "@/lib/api"
import { Card } from "@/components/ui"

function StatusMark({ status }: { status: DossierClaim["status"] }) {
  const ok = status === "supported"
  return (
    <span
      title={ok ? "corpus-supported" : "needs clinician verification"}
      className={`mt-0.5 select-none font-mono text-sm ${ok ? "text-success-ink" : "text-amber-ink"}`}
    >
      {ok ? "✓" : "⚠"}
    </span>
  )
}

function Claim({ claim }: { claim: DossierClaim }) {
  return (
    <li className="flex gap-3">
      <StatusMark status={claim.status} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="reading !text-[0.98rem] !leading-snug">{claim.text}</span>
          {claim.figure_ids.map((fid) => (
            <a
              key={fid}
              href={`#${fid}`}
              className="border-2 border-border bg-primary px-1.5 font-mono text-[10px] font-bold text-primary-foreground"
            >
              {fid}
            </a>
          ))}
        </div>
        {claim.why && (
          <p className="mt-1.5 border-l-2 border-border pl-3 font-serif text-sm leading-relaxed text-muted-foreground">
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              Why
            </span>{" "}
            {claim.why}
          </p>
        )}
        {claim.sub_items.length > 0 && (
          <ul className="mt-2 flex flex-col gap-1">
            {claim.sub_items.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                <span className="mt-0.5 select-none font-mono text-muted-foreground">☐</span>
                <span className="font-serif leading-relaxed">{s}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  )
}

function FigureCard({ fig }: { fig: DossierFigure }) {
  const show = fig.image_url && fig.image_available
  return (
    <figure
      id={fig.fig_id}
      className="surface scroll-mt-24 overflow-hidden transition-colors hover:border-primary"
    >
      <div className="flex aspect-[4/3] items-center justify-center bg-background">
        {show ? (
          <img
            src={fig.image_url!}
            alt={fig.caption || fig.citation}
            loading="lazy"
            className="h-full w-full object-contain"
          />
        ) : (
          <span className="px-4 text-center font-mono text-xs text-muted-foreground">
            image unavailable
          </span>
        )}
      </div>
      <figcaption className="space-y-1 p-3.5">
        <span className="font-mono text-[10px] uppercase tracking-wider text-primary-ink">
          {fig.fig_id} · {fig.citation}
        </span>
        {fig.caption && <p className="text-xs leading-snug text-muted-foreground">{fig.caption}</p>}
        {fig.claim_ref && (
          <p className="text-[11px] text-muted-foreground">
            <span className="font-mono uppercase tracking-wider">supports:</span> {fig.claim_ref}
          </p>
        )}
      </figcaption>
    </figure>
  )
}

function Section({ section }: { section: DossierSection }) {
  return (
    <Card className="p-6">
      <h2 className="font-display text-xl font-bold text-foreground">{section.heading}</h2>
      {section.intro && <p className="mt-1 text-sm text-muted-foreground">{section.intro}</p>}
      {section.claims.length > 0 && (
        <ul className="mt-5 flex flex-col gap-4">
          {section.claims.map((c, i) => (
            <Claim key={i} claim={c} />
          ))}
        </ul>
      )}
      {section.figures.length > 0 && (
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {section.figures.map((f) => (
            <FigureCard key={f.fig_id} fig={f} />
          ))}
        </div>
      )}
    </Card>
  )
}

export default function DossierView({ dossier }: { dossier: Dossier }) {
  const appendix = dossier.appendix.entries
  return (
    <div className="flex flex-col gap-5">
      {dossier.sections.map((s, i) => (
        <Section key={i} section={s} />
      ))}

      {appendix.length > 0 && (
        <Card className="bg-card p-6">
          <h2 className="eyebrow">Appendix</h2>
          <div className="mt-3 flex flex-col gap-4">
            {appendix.map((e, i) => (
              <div key={i}>
                <h3 className="text-sm font-semibold text-foreground">{e.heading}</h3>
                {e.items.length > 0 && (
                  <ul className="mt-1 ml-5 list-disc font-serif text-sm text-muted-foreground">
                    {e.items.map((it, j) => (
                      <li key={j}>{it}</li>
                    ))}
                  </ul>
                )}
                {e.sources.length > 0 && (
                  <ul className="mt-1 ml-5 list-disc font-serif text-sm text-muted-foreground">
                    {e.sources.map((src, j) => (
                      <li key={j}>{src}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
