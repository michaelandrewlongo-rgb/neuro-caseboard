type Props = { eyebrow: string; title: string; blurb: string; milestone: string }

/** Honest placeholder for a surface not yet wired to its engine lane. M0 ships the shell;
    M1–M3 replace these with the real Ask / Build / Cards calls. No fake content. */
export default function SurfaceStub({ eyebrow, title, blurb, milestone }: Props) {
  return (
    <div className="flex flex-col gap-4">
      <p className="font-mono text-xs uppercase tracking-[0.3em] text-teal">{eyebrow}</p>
      <h1 className="font-display text-4xl font-bold tracking-tight text-ink">{title}</h1>
      <p className="max-w-2xl text-ink-dim">{blurb}</p>
      <div className="mt-2 w-fit rounded-md border border-navy-700/60 bg-navy-900/50 px-3 py-2 font-mono text-xs text-ink-faint">
        Not yet wired · arrives in {milestone}
      </div>
    </div>
  )
}
