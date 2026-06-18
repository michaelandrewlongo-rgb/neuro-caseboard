import type { Card } from "@/lib/api"

export default function CardItem({ card, index }: { card: Card; index: number }) {
  const images = card.images.filter((im) => im.image_available && im.image_url)
  return (
    <article className="rounded-xl border border-navy-700/60 bg-navy-900/50 p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-ink-faint">[{index + 1}]</span>
        <span className="rounded-full bg-navy-800 px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-ink-dim">
          {card.deck}
        </span>
        {card.tags && (
          <span className="font-mono text-[10px] text-ink-faint">{card.tags}</span>
        )}
      </div>

      {card.flagged.length > 0 && (
        <div className="mb-3 rounded-md border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-xs text-amber-300">
          ⚠ Flagged in your deck as unverified ({card.flagged.join(", ")}) — not source-checked.
        </div>
      )}

      {card.question_text && (
        <p className="text-ink">
          <span className="font-mono text-xs uppercase tracking-wider text-teal">Q.</span>{" "}
          {card.question_text}
        </p>
      )}
      {card.answer_text && (
        <p className="mt-2 whitespace-pre-wrap text-ink-dim">
          <span className="font-mono text-xs uppercase tracking-wider text-ink-faint">A.</span>{" "}
          {card.answer_text}
        </p>
      )}

      {images.length > 0 && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {images.map((im, i) => (
            <img
              key={i}
              src={im.image_url!}
              alt={`card ${index + 1} media ${i + 1}`}
              loading="lazy"
              className="w-full rounded-lg border border-navy-700/60 bg-navy-950/60 object-contain"
            />
          ))}
        </div>
      )}
    </article>
  )
}
