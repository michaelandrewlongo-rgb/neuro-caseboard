import { useEffect, useReducer, useRef, useState } from "react"
import { searchCards, type Card, type CardsResponse } from "@/lib/api"
import { cardsQueryReducer, initialCardsQuery } from "@/lib/cardsQuery"
import { EvidenceGauge } from "@/components/charts/EvidenceGauge"
import PipelineLoader from "@/components/PipelineLoader"
import CardItem from "@/components/cards/CardItem"

// ── Constants ──────────────────────────────────────────────────────────────────

const HINTS = ["cavernous sinus contents", "Meckel cave", "spinal cord tracts", "circle of Willis"]

const CARDS_STEPS = [
  "Embedding your query…",
  "Hybrid search over the card bank…",
  "Re-ranking the closest matches…",
]

// ── Types ──────────────────────────────────────────────────────────────────────

type DeckFilter = "all" | "sans" | "abns" | "high-yield"

// ── Helpers ────────────────────────────────────────────────────────────────────

/** Returns true only if the card's flagged array marks it high-yield. */
function isHighYield(card: Card): boolean {
  return card.flagged.some((f) => f.toLowerCase().replace(/[-\s]/g, "") === "highyield")
}

/** Filter the displayed card list by deck type or yield flag. */
function filterCards(cards: Card[], filter: DeckFilter): Card[] {
  switch (filter) {
    case "sans":
      return cards.filter((c) => c.deck.toUpperCase().includes("SANS"))
    case "abns":
      return cards.filter((c) => c.deck.toUpperCase().includes("ABNS"))
    case "high-yield":
      return cards.filter(isHighYield)
    default:
      return cards
  }
}

/** Derive category counts from deck names in results. */
function getDeckCoverage(cards: Card[]) {
  const counts = { tumor: 0, functional: 0, vascular: 0, spine: 0 }
  for (const c of cards) {
    const d = c.deck.toLowerCase()
    if (d.includes("tumor") || d.includes("oncol") || d.includes("neuro-onc")) {
      counts.tumor++
    } else if (
      d.includes("funct") ||
      d.includes("epilep") ||
      d.includes("movement") ||
      d.includes("pain")
    ) {
      counts.functional++
    } else if (
      d.includes("vascular") ||
      d.includes("aneurysm") ||
      d.includes("avm") ||
      d.includes("stroke")
    ) {
      counts.vascular++
    } else if (d.includes("spine") || d.includes("spinal") || d.includes("cord")) {
      counts.spine++
    }
  }
  return counts
}

// ── Deck filter chip config ────────────────────────────────────────────────────

const DECK_FILTER_OPTIONS: { key: DeckFilter; label: string; ochre?: boolean }[] = [
  { key: "all", label: "ALL DECKS" },
  { key: "sans", label: "SANS" },
  { key: "abns", label: "ABNS" },
  { key: "high-yield", label: "★ HIGH-YIELD", ochre: true },
]

// ── Page ───────────────────────────────────────────────────────────────────────

export default function Cards() {
  // BACKLOG P4 #11: single source of truth for the query box (visible input == internal state).
  const [{ question, submitted }, dispatch] = useReducer(cardsQueryReducer, initialCardsQuery)
  const [k, setK] = useState(6)
  const [loading, setLoading] = useState(false)
  const [resp, setResp] = useState<CardsResponse | null>(null)
  const [netError, setNetError] = useState<string | null>(null)
  const [deckFilter, setDeckFilter] = useState<DeckFilter>("all")
  const ctrlRef = useRef<AbortController | null>(null)

  useEffect(() => () => ctrlRef.current?.abort(), [])

  async function run(q: string) {
    const text = q.trim()
    if (!text || loading) return
    ctrlRef.current?.abort()
    const ctrl = new AbortController()
    ctrlRef.current = ctrl
    dispatch({ type: "selectChip", text }) // sync the visible input to the run query
    dispatch({ type: "submit" }) // submitted is derived from question — they cannot diverge
    setResp(null)
    setNetError(null)
    setLoading(true)
    try {
      const r = await searchCards(text, k, ctrl.signal)
      if (!ctrl.signal.aborted) setResp(r)
    } catch (e) {
      const err = e as { name?: string; message?: string }
      if (err?.name !== "AbortError") setNetError(err?.message ?? String(e))
    } finally {
      if (!ctrl.signal.aborted) setLoading(false)
    }
  }

  /* Screen-reader live region */
  const liveMsg = loading
    ? ""
    : netError
      ? "Request failed."
      : resp
        ? resp.kind === "cards"
          ? `${resp.cards.length} card${resp.cards.length === 1 ? "" : "s"} found.`
          : resp.kind === "not_built"
            ? "Card bank not built."
            : resp.kind === "unavailable"
              ? "Engine temporarily unavailable."
              : "Engine error."
        : ""

  return (
    <div className="flex flex-col gap-8">
      {/* Persistent live region: announces match results to screen readers */}
      <div aria-live="polite" className="sr-only">
        {liveMsg}
      </div>

      {/* ── Hero ── */}
      <header className="flex flex-col gap-5">
        <p
          className="font-mono text-[11px] font-bold uppercase tracking-[0.18em]"
          style={{ color: "#e0a86a" }}
        >
          CARDS · BOARD-REVIEW DECK
        </p>
        <div>
          <h1
            className="font-display text-[2.4rem] font-semibold leading-tight"
            style={{ color: "#f1ece6", letterSpacing: "-0.02em" }}
          >
            Search your card bank
          </h1>
          <p className="mt-2 max-w-xl text-base" style={{ color: "#a79e98", lineHeight: "1.6" }}>
            Hybrid search over your personal ABNS / SANS deck — your own study cards, matched,
            never synthesized.
          </p>
        </div>

        {/* ── Search form ── */}
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void run(question)
          }}
          className="flex flex-col gap-3"
        >
          {/* Input row */}
          <div className="flex gap-3">
            <input
              type="text"
              value={question}
              onChange={(e) => dispatch({ type: "type", text: e.target.value })}
              placeholder='e.g. "cavernous sinus contents"'
              className="field flex-1"
              disabled={loading}
              autoFocus
            />
            {/* Crimson Search button */}
            <button
              type="submit"
              disabled={loading || !question.trim()}
              style={{
                background:
                  loading || !question.trim()
                    ? "rgba(255,255,255,0.06)"
                    : "linear-gradient(135deg,#d8413a,#ff7363)",
                color: loading || !question.trim() ? "#978d86" : "#ffffff",
                border: "none",
                borderRadius: "var(--radius-md)",
                padding: "0.75rem 1.5rem",
                fontFamily: "var(--font-mono)",
                fontSize: "11px",
                fontWeight: 700,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                cursor: loading || !question.trim() ? "not-allowed" : "pointer",
                whiteSpace: "nowrap",
                boxShadow:
                  loading || !question.trim() ? "none" : "0 6px 22px rgba(216,65,58,.32)",
                transition: "background 0.15s, box-shadow 0.15s",
              }}
            >
              {loading ? "Searching…" : "Search"}
            </button>
          </div>

          {/* k slider (preserve existing flow) */}
          <label
            className="flex items-center gap-3 text-sm"
            style={{ color: "#978d86" }}
          >
            <span className="font-mono text-[11px] uppercase tracking-wider">Cards to show</span>
            <input
              type="range"
              min={3}
              max={20}
              value={k}
              onChange={(e) => setK(Number(e.target.value))}
              disabled={loading}
              className="accent-secondary flex-1"
            />
            <span className="tnum font-mono" style={{ color: "#f1ece6" }}>
              {k}
            </span>
          </label>

          {/* Deck filter chips */}
          <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by deck">
            {DECK_FILTER_OPTIONS.map(({ key, label, ochre }) => {
              const isActive = deckFilter === key
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setDeckFilter(key)}
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "10px",
                    fontWeight: 700,
                    letterSpacing: "0.14em",
                    textTransform: "uppercase",
                    padding: "0.35rem 0.75rem",
                    borderRadius: "var(--radius-sm)",
                    border: isActive
                      ? "1px solid rgba(63,150,144,.5)"
                      : ochre
                        ? "1px solid rgba(216,154,63,.3)"
                        : "1px solid rgba(255,255,255,.09)",
                    background: isActive
                      ? "rgba(63,150,144,.15)"
                      : ochre
                        ? "rgba(216,154,63,.06)"
                        : "rgba(255,255,255,.04)",
                    color: isActive ? "#6fc0b8" : ochre ? "#e0a86a" : "#a79e98",
                    cursor: "pointer",
                    transition: "all 0.15s",
                  }}
                  aria-pressed={isActive}
                >
                  {label}
                </button>
              )
            })}
          </div>
        </form>

        {/* Hint chips */}
        {!submitted && !loading && (
          <div className="flex flex-wrap gap-2">
            {HINTS.map((h) => (
              <button key={h} onClick={() => void run(h)} className="chip">
                {h}
              </button>
            ))}
          </div>
        )}
      </header>

      {/* ── Loading ── */}
      {loading && (
        <PipelineLoader steps={CARDS_STEPS} bars={4} estimate="Usually 10–40 seconds." />
      )}

      {/* ── Net error ── */}
      {netError && !loading && (
        <div
          className="surface"
          style={{
            padding: "1.25rem",
            background:
              "linear-gradient(160deg, rgba(255,255,255,.05), rgba(255,255,255,.012))",
            border: "1px solid rgba(255,255,255,.09)",
            borderRadius: "var(--radius-lg)",
          }}
        >
          <p
            className="font-mono text-xs font-bold uppercase tracking-wider"
            style={{ color: "#ff7363" }}
          >
            Request failed
          </p>
          <p className="mt-1 text-sm" style={{ color: "#978d86" }}>
            {netError}
          </p>
          <p className="mt-2 font-mono text-xs" style={{ color: "#766a64" }}>
            Is the engine wrapper running on :8001?
          </p>
        </div>
      )}

      {/* ── Results ── */}
      {resp && !loading && <CardsResult resp={resp} deckFilter={deckFilter} k={k} />}
    </div>
  )
}

// ── Deck Telemetry ─────────────────────────────────────────────────────────────

function DeckTelemetry({ cards }: { cards: Card[] }) {
  const total = cards.length
  const highYieldCount = cards.filter(isHighYield).length
  const coverage = getDeckCoverage(cards)
  const maxCount = Math.max(
    coverage.tumor,
    coverage.functional,
    coverage.vascular,
    coverage.spine,
    1,
  )
  const allZero = Object.values(coverage).every((v) => v === 0)

  // Match strength: no score field in CardsResponse — show honest unavailable state.
  const gaugeRings = [
    { r: 52, frac: 0, color: "rgba(63,150,144,.2)", glow: "rgba(63,150,144,.05)" },
  ]

  const coverageBars = [
    { label: "Tumor", count: coverage.tumor, color: "#5fa86f" },
    { label: "Functional", count: coverage.functional, color: "#6fc0b8" },
    { label: "Vascular", count: coverage.vascular, color: "#e0a86a" },
    { label: "Spine", count: coverage.spine, color: "#c0564f" },
  ]

  const glassPanel: React.CSSProperties = {
    background: "linear-gradient(160deg, rgba(255,255,255,.05), rgba(255,255,255,.012))",
    border: "1px solid rgba(255,255,255,.09)",
    borderRadius: "var(--radius-lg)",
    padding: "1.25rem",
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 1.1fr 1fr",
        gap: "1rem",
      }}
    >
      {/* ── Match Strength ── */}
      <div style={{ ...glassPanel, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
          style={{ color: "#a79e98" }}
        >
          Match Strength
        </p>
        <div className="flex flex-col items-center gap-2">
          <EvidenceGauge rings={gaugeRings} size={130}>
            <div className="flex flex-col items-center gap-0.5">
              <span className="font-mono text-xs font-bold" style={{ color: "#6fc0b8" }}>
                N/A
              </span>
              <span
                className="font-mono"
                style={{
                  fontSize: "9px",
                  color: "#766a64",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                }}
              >
                COSINE
              </span>
            </div>
          </EvidenceGauge>
        </div>
        <p
          className="font-mono text-[9px] text-center"
          style={{ color: "#766a64", letterSpacing: "0.1em" }}
        >
          Score not returned by API
        </p>
      </div>

      {/* ── Deck Coverage ── */}
      <div
        style={{ ...glassPanel, display: "flex", flexDirection: "column", gap: "0.75rem" }}
      >
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
          style={{ color: "#a79e98" }}
        >
          Deck Coverage
        </p>
        <p className="font-mono text-[9px]" style={{ color: "#766a64" }}>
          Cards in results by category
        </p>
        {coverageBars.map(({ label, count, color }) => (
          <div key={label} className="flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <span
                className="font-mono text-[9px] uppercase tracking-wider"
                style={{ color: "#978d86" }}
              >
                {label}
              </span>
              <span className="tnum font-mono text-[10px]" style={{ color }}>
                {count}
              </span>
            </div>
            <div
              style={{
                height: "4px",
                background: "rgba(255,255,255,.07)",
                borderRadius: "2px",
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${(count / maxCount) * 100}%`,
                  background: color,
                  borderRadius: "2px",
                  boxShadow: `0 0 6px ${color}60`,
                  transition: "width 0.4s cubic-bezier(.22,1,.36,1)",
                }}
              />
            </div>
          </div>
        ))}
        {allZero && (
          <p className="font-mono text-[9px]" style={{ color: "#766a64" }}>
            No category keywords matched deck names
          </p>
        )}
      </div>

      {/* ── Deck Status ── */}
      <div
        style={{ ...glassPanel, display: "flex", flexDirection: "column", gap: "0.75rem" }}
      >
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
          style={{ color: "#a79e98" }}
        >
          Deck Status
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
          <div
            style={{
              background: "rgba(63,150,144,.07)",
              border: "1px solid rgba(63,150,144,.2)",
              borderRadius: "var(--radius-md)",
              padding: "0.75rem",
            }}
          >
            <div
              className="tnum font-display text-2xl font-semibold"
              style={{ color: "#6fc0b8" }}
            >
              {total}
            </div>
            <div
              className="font-mono text-[9px] uppercase tracking-wider mt-1"
              style={{ color: "#978d86" }}
            >
              Matched
            </div>
          </div>
          <div
            style={{
              background: "rgba(216,154,63,.06)",
              border: "1px solid rgba(216,154,63,.2)",
              borderRadius: "var(--radius-md)",
              padding: "0.75rem",
            }}
          >
            <div
              className="tnum font-display text-2xl font-semibold"
              style={{ color: "#e0a86a" }}
            >
              {highYieldCount}
            </div>
            <div
              className="font-mono text-[9px] uppercase tracking-wider mt-1"
              style={{ color: "#978d86" }}
            >
              High-Yield
            </div>
          </div>
        </div>
        <p className="font-mono text-[9px]" style={{ color: "#766a64" }}>
          From this result set only
        </p>
      </div>
    </div>
  )
}

// ── CardsResult ────────────────────────────────────────────────────────────────

function CardsResult({
  resp,
  deckFilter,
  k,
}: {
  resp: CardsResponse
  deckFilter: DeckFilter
  k: number
}) {
  const degradedStyle: React.CSSProperties = {
    background: "rgba(255,255,255,.04)",
    border: "1px solid rgba(255,255,255,.09)",
    borderRadius: "var(--radius-lg)",
    padding: "1.25rem",
  }

  if (resp.kind === "error") {
    return (
      <div style={degradedStyle}>
        <p
          className="font-mono text-xs font-bold uppercase tracking-wider"
          style={{ color: "#ff7363" }}
        >
          Engine error
        </p>
        <p className="mt-1 font-mono text-xs" style={{ color: "#978d86" }}>
          {resp.error}
        </p>
      </div>
    )
  }

  if (resp.kind === "unavailable") {
    return (
      <div style={degradedStyle}>
        <p className="font-semibold" style={{ color: "#f1ece6" }}>
          Temporarily unavailable
        </p>
        <p className="mt-1 text-sm" style={{ color: "#978d86" }}>
          {resp.reason}
        </p>
      </div>
    )
  }

  if (resp.kind === "not_built") {
    return (
      <div style={degradedStyle}>
        <p className="font-semibold" style={{ color: "#f1ece6" }}>
          Card bank not built
        </p>
        <p className="mt-1 whitespace-pre-wrap font-mono text-xs" style={{ color: "#978d86" }}>
          {resp.reason}
        </p>
      </div>
    )
  }

  const allCards = resp.cards

  if (!allCards.length) {
    return (
      <div style={degradedStyle}>
        <p className="text-sm" style={{ color: "#978d86" }}>
          No matching cards.
        </p>
      </div>
    )
  }

  const displayCards = filterCards(allCards, deckFilter)
  /* If we got exactly k cards back the deck may have more beyond the limit */
  const mayHaveMore = allCards.length >= k

  return (
    <div className="flex flex-col gap-6">
      <DeckTelemetry cards={allCards} />

      {/* Section header */}
      <div className="flex items-center justify-between">
        <p
          className="font-mono text-[11px] font-bold uppercase tracking-[0.18em]"
          style={{ color: "#e0a86a" }}
        >
          Matched Cards
          {displayCards.length !== allCards.length && (
            <span style={{ color: "#978d86", fontWeight: 400 }}>
              {" "}
              — {displayCards.length} of {allCards.length}
            </span>
          )}
        </p>
        <span className="font-mono text-[10px]" style={{ color: "#766a64" }}>
          {displayCards.length} card{displayCards.length !== 1 ? "s" : ""}
        </span>
      </div>

      {displayCards.length === 0 ? (
        <p className="text-sm" style={{ color: "#978d86" }}>
          No cards match this filter.
        </p>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          {displayCards.map((c) => {
            const origIdx = allCards.indexOf(c)
            return (
              <CardItem key={c.id || origIdx} card={c} index={origIdx} total={allCards.length} />
            )
          })}

          {/* Dashed "+ N more below threshold" tile */}
          {mayHaveMore && (
            <div
              style={{
                border: "1px dashed rgba(255,255,255,.12)",
                borderRadius: "var(--radius-lg)",
                padding: "1.5rem",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "rgba(255,255,255,.02)",
              }}
            >
              <span
                className="font-mono text-[11px] font-bold uppercase tracking-wider"
                style={{ color: "#766a64" }}
              >
                + more in deck — increase range to see
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
