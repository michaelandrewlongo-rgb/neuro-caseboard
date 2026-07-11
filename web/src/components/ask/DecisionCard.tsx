import { useState } from "react"
import type { Citation, DecisionCard as DecisionCardData, ReviewedClaim } from "@/lib/api"
import { claimReason, firstPageUrl, hasCardContent } from "@/lib/decisionCard"

// Grounded-Anatomical palette (matches AnswerView's inline tones): blue heads, green = settled,
// amber = verify. Colored text sits on the dark console surface, so amber/green text is legible
// (the two-token -ink rule is for colored text on LIGHT surfaces only).
const INK = "#ededed"
const BLUE = "#6b93ff"
const AMBER = "#ffc94d"
const GREEN = "#34e07f"
const MUTED = "rgba(237,237,237,.55)"

function Markers({ markers }: { markers: string[] }) {
  if (!markers.length) return null
  return (
    <span className="ml-1.5 inline-flex gap-1 align-middle">
      {markers.map((m) => (
        <span
          key={m}
          className="rounded-[var(--radius-sm)] px-1.5 py-0.5 font-mono text-[10px] font-bold"
          style={{ background: "rgba(107,147,255,.14)", color: BLUE }}
        >
          [{m}]
        </span>
      ))}
    </span>
  )
}

// Click-to-source: the model's verbatim supporting sentence (§3.3) and, for a textbook [n]
// citation, the rendered folio image (§3.4, SP2b). One toggle reveals both when present.
function ClaimSource({ quote, pageUrl }: { quote: string; pageUrl: string | null }) {
  const [open, setOpen] = useState(false)
  if (!quote && !pageUrl) return null
  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="font-mono text-[10px] uppercase tracking-[0.14em] transition-colors hover:opacity-80"
        style={{ color: MUTED }}
      >
        {open ? "▾ hide source" : "▸ show source"}
      </button>
      {open && (
        <div className="mt-1.5 space-y-2">
          {quote && (
            <blockquote
              className="border-l-2 pl-3 text-[13px] italic"
              style={{ borderColor: "rgba(237,237,237,.2)", color: MUTED }}
            >
              &ldquo;{quote}&rdquo;
            </blockquote>
          )}
          {pageUrl && (
            <img
              src={pageUrl}
              loading="lazy"
              alt="cited textbook page"
              className="max-w-full rounded-[var(--radius-sm)]"
              style={{ border: "1px solid rgba(255,255,255,.1)", maxHeight: "480px" }}
            />
          )}
        </div>
      )}
    </div>
  )
}

function Lane({ label, color, children }: { label: string; color: string; children: React.ReactNode }) {
  return (
    <div className="mt-5 first:mt-4">
      <h3
        className="mb-2 font-display text-[13px] font-bold uppercase tracking-[0.14em]"
        style={{ color }}
      >
        {label}
      </h3>
      {children}
    </div>
  )
}

function SettledClaim({ c, sources }: { c: ReviewedClaim; sources: Citation[] }) {
  return (
    <li className="flex gap-2.5">
      <span aria-hidden className="mt-[3px] text-[10px]" style={{ color: GREEN }}>
        ●
      </span>
      <div className="min-w-0">
        <span style={{ color: INK, fontSize: "14.5px", lineHeight: 1.62 }}>{c.text}</span>
        <Markers markers={c.markers} />
        {c.year != null && (
          <span className="ml-1 font-mono text-[11px]" style={{ color: MUTED }}>
            ({c.year})
          </span>
        )}
        <ClaimSource quote={c.quote} pageUrl={firstPageUrl(c.markers, sources)} />
      </div>
    </li>
  )
}

function UncertainClaim({ c, sources }: { c: ReviewedClaim; sources: Citation[] }) {
  return (
    <li className="flex gap-2.5">
      <span aria-hidden className="mt-[3px] text-[10px]" style={{ color: AMBER }}>
        ▲
      </span>
      <div className="min-w-0">
        <span style={{ color: INK, fontSize: "14.5px", lineHeight: 1.62 }}>{c.text}</span>
        <Markers markers={c.markers} />
        <p className="mt-0.5 text-[12.5px]" style={{ color: AMBER }}>
          verify — {claimReason(c)}
        </p>
        <ClaimSource quote={c.quote} pageUrl={firstPageUrl(c.markers, sources)} />
      </div>
    </li>
  )
}

export default function DecisionCard({
  card,
  sources = [],
}: {
  card: DecisionCardData
  sources?: Citation[]
}) {
  if (!hasCardContent(card)) return null
  const showUncertain = card.uncertainties.length > 0 || card.coverage_gaps.length > 0
  return (
    <section
      aria-label="Decision summary"
      className="rounded-[var(--radius-lg)] p-6 sm:p-7"
      style={{
        background: "linear-gradient(160deg, rgba(107,147,255,.06), rgba(255,255,255,.012))",
        border: "1px solid rgba(255,255,255,.09)",
      }}
    >
      <p
        className="font-mono text-[10px] font-bold uppercase tracking-[0.2em]"
        style={{ color: BLUE }}
      >
        Decision Card
      </p>

      {card.bottom_line.length > 0 && (
        <Lane label="Bottom line" color={GREEN}>
          <ul className="space-y-2.5">
            {card.bottom_line.map((c, i) => (
              <SettledClaim key={i} c={c} sources={sources} />
            ))}
          </ul>
        </Lane>
      )}

      {card.decision_furniture.length > 0 && (
        <Lane label="What changes the decision" color={BLUE}>
          <ul className="space-y-2.5">
            {card.decision_furniture.map((c, i) => (
              <SettledClaim key={i} c={c} sources={sources} />
            ))}
          </ul>
        </Lane>
      )}

      {showUncertain && (
        <Lane label="Uncertain — verify current guidance" color={AMBER}>
          <ul className="space-y-3">
            {card.uncertainties.map((c, i) => (
              <UncertainClaim key={i} c={c} sources={sources} />
            ))}
          </ul>
          {card.coverage_gaps.map((g, i) => (
            <p key={i} className="mt-2 pl-[18px] text-[12.5px]" style={{ color: AMBER }}>
              ▲ {g}
            </p>
          ))}
        </Lane>
      )}

      {card.conflicts.length > 0 && (
        <Lane label="Conflicting sources" color={AMBER}>
          <ul className="space-y-1.5">
            {card.conflicts.map((c, i) => (
              <li key={i} className="text-[13px]" style={{ color: MUTED }}>
                {c}
              </li>
            ))}
          </ul>
        </Lane>
      )}
    </section>
  )
}
