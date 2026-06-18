import type { Card as CardData } from "@/lib/api"
import { Card, Badge } from "@/components/ui"

export default function CardItem({ card, index }: { card: CardData; index: number }) {
  const images = card.images.filter((im) => im.image_available && im.image_url)
  return (
    <Card className="p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-muted-foreground">[{index + 1}]</span>
        <Badge tone="neutral">{card.deck}</Badge>
        {card.tags && <span className="font-mono text-[10px] text-muted-foreground">{card.tags}</span>}
      </div>

      {card.flagged.length > 0 && (
        <div className="mb-3 border-2 border-border bg-secondary px-3 py-2 text-xs font-medium text-foreground">
          ⚠ Flagged in your deck as unverified ({card.flagged.join(", ")}) — not source-checked.
        </div>
      )}

      {card.question_text && (
        <p className="reading">
          <span className="mr-1 font-mono text-xs uppercase tracking-wider text-primary-ink">Q.</span>
          {card.question_text}
        </p>
      )}
      {card.answer_text && (
        <p className="reading mt-2 whitespace-pre-wrap !text-muted-foreground">
          <span className="mr-1 font-mono text-xs uppercase tracking-wider text-muted-foreground">A.</span>
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
              className="w-full border-2 border-border bg-background object-contain"
            />
          ))}
        </div>
      )}
    </Card>
  )
}
