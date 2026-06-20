import type { Card as CardData } from "@/lib/api"

/** Returns true only when the card's flagged list marks it high-yield. */
function cardIsHighYield(card: CardData): boolean {
  return card.flagged.some((f) => f.toLowerCase().replace(/[-\s]/g, "") === "highyield")
}

/**
 * Rank-based match tier: the API returns cards in descending relevance order.
 * Top third = strong (sage), middle = moderate (ochre), rest = weak (muted).
 * This is derived from real ranking data, not a fabricated numeric score.
 */
function matchTier(index: number, total: number): "strong" | "moderate" | "weak" {
  const pct = total > 1 ? index / (total - 1) : 0
  if (pct < 0.34) return "strong"
  if (pct < 0.67) return "moderate"
  return "weak"
}

const TIER_COLOR: Record<"strong" | "moderate" | "weak", string> = {
  strong: "#74c084",   // sage bright
  moderate: "#e0a86a", // ochre on-dark
  weak: "#766a64",     // muted mono
}

const TIER_LABEL: Record<"strong" | "moderate" | "weak", string> = {
  strong: "TOP MATCH",
  moderate: "GOOD MATCH",
  weak: "MATCH",
}

export default function CardItem({
  card,
  index,
  total,
}: {
  card: CardData
  index: number
  total: number
}) {
  const images = card.images.filter((im) => im.image_available && im.image_url)
  const highYield = cardIsHighYield(card)
  const tier = matchTier(index, total)
  const tierColor = TIER_COLOR[tier]
  const tierLabel = TIER_LABEL[tier]

  // Parse comma-separated tags string
  const tags = card.tags
    ? card.tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean)
    : []

  return (
    <div
      style={{
        background: "linear-gradient(160deg, rgba(255,255,255,.05), rgba(255,255,255,.012))",
        border: "1px solid rgba(255,255,255,.09)",
        borderRadius: "var(--radius-lg)",
        padding: "1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.75rem",
        transition: "transform 0.15s, border-color 0.15s",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = "translateY(-2px)"
        e.currentTarget.style.borderColor = "rgba(63,150,144,.4)"
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = "translateY(0)"
        e.currentTarget.style.borderColor = "rgba(255,255,255,.09)"
      }}
    >
      {/* ── Badge row ── */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Teal deck badge */}
        <span
          className="font-mono text-[10px] font-bold uppercase tracking-wider"
          style={{
            background: "rgba(63,150,144,.15)",
            border: "1px solid rgba(63,150,144,.35)",
            borderRadius: "var(--radius-sm)",
            padding: "0.2rem 0.55rem",
            color: "#6fc0b8",
          }}
        >
          {card.deck}
        </span>

        {/* ★ HIGH-YIELD — only when flagged field marks it */}
        {highYield && (
          <span
            className="font-mono text-[10px] font-bold uppercase tracking-wider"
            style={{
              background: "rgba(216,154,63,.1)",
              border: "1px solid rgba(216,154,63,.35)",
              borderRadius: "var(--radius-sm)",
              padding: "0.2rem 0.55rem",
              color: "#e0a86a",
            }}
          >
            ★ HIGH-YIELD
          </span>
        )}

        {/* Match tier (rank-based, not a fabricated score) */}
        <span
          className="font-mono text-[9px] font-bold uppercase tracking-wider"
          style={{
            marginLeft: "auto",
            color: tierColor,
          }}
        >
          {tierLabel}
        </span>
      </div>

      {/* ── PROMPT ── */}
      {card.question_text && (
        <div>
          <p
            className="font-mono text-[9px] font-bold uppercase tracking-[0.18em] mb-1"
            style={{ color: "#ff7363" }}
          >
            PROMPT
          </p>
          <p className="text-sm leading-[1.6]" style={{ color: "#f1ece6" }}>
            {card.question_text}
          </p>
        </div>
      )}

      {/* ── ANSWER ── */}
      {card.answer_text && (
        <div>
          <p
            className="font-mono text-[9px] font-bold uppercase tracking-[0.18em] mb-1"
            style={{ color: "#74c084" }}
          >
            ANSWER
          </p>
          <p
            className="text-sm leading-[1.6] whitespace-pre-wrap"
            style={{ color: "#a79e98" }}
          >
            {card.answer_text}
          </p>
        </div>
      )}

      {/* ── Flagged warning (non-high-yield flags) ── */}
      {card.flagged.length > 0 && !highYield && (
        <div
          style={{
            background: "rgba(192,86,79,.08)",
            border: "1px solid rgba(192,86,79,.25)",
            borderRadius: "var(--radius-sm)",
            padding: "0.5rem 0.75rem",
          }}
        >
          <p className="font-mono text-[9px] uppercase tracking-wider" style={{ color: "#c0564f" }}>
            Flagged: {card.flagged.join(", ")} — not source-checked
          </p>
        </div>
      )}

      {/* ── Tag chips ── */}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag, i) => (
            <span
              key={i}
              className="font-mono text-[9px] uppercase tracking-wider"
              style={{
                background: "rgba(255,255,255,.04)",
                border: "1px solid rgba(255,255,255,.09)",
                borderRadius: "var(--radius-sm)",
                padding: "0.18rem 0.5rem",
                color: "#766a64",
              }}
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* ── Images ── */}
      {images.length > 0 && (
        <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))" }}>
          {images.map((im, i) => (
            <img
              key={i}
              src={im.image_url!}
              alt={`card ${index + 1} media ${i + 1}`}
              loading="lazy"
              style={{
                width: "100%",
                border: "1px solid rgba(255,255,255,.09)",
                borderRadius: "var(--radius-sm)",
                background: "rgba(255,255,255,.02)",
                objectFit: "contain",
              }}
            />
          ))}
        </div>
      )}
    </div>
  )
}
