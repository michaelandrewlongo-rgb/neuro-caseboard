import { useEffect, useRef, useState } from "react"
import { searchCards, type CardsResponse } from "@/lib/api"
import PipelineLoader from "@/components/PipelineLoader"
import CardItem from "@/components/cards/CardItem"

const HINTS = [
  "cavernous sinus contents",
  "Meckel cave",
  "spinal cord tracts",
  "circle of Willis",
]

const CARDS_STEPS = [
  "Embedding your query…",
  "Hybrid search over the card bank…",
  "Re-ranking the closest matches…",
]

export default function Cards() {
  const [question, setQuestion] = useState("")
  const [submitted, setSubmitted] = useState<string | null>(null)
  const [k, setK] = useState(6)
  const [loading, setLoading] = useState(false)
  const [resp, setResp] = useState<CardsResponse | null>(null)
  const [netError, setNetError] = useState<string | null>(null)
  const ctrlRef = useRef<AbortController | null>(null)

  useEffect(() => () => ctrlRef.current?.abort(), [])

  async function run(q: string) {
    const text = q.trim()
    if (!text || loading) return
    ctrlRef.current?.abort()
    const ctrl = new AbortController()
    ctrlRef.current = ctrl
    setSubmitted(text)
    setQuestion(text)
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

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="font-mono text-xs uppercase tracking-[0.3em] text-teal">Cards · Study deck</p>
        <h1 className="mt-2 font-display text-4xl font-bold tracking-tight text-ink">
          Board-review card bank
        </h1>
        <p className="mt-2 max-w-2xl text-ink-dim">
          Hybrid search over your personal ABNS / SANS deck — your own study notes, matched but not
          synthesized.
        </p>
        <div className="mt-3 rounded-md border border-navy-700/60 bg-navy-900/50 px-4 py-3 text-sm text-ink-dim">
          <span className="font-mono text-xs uppercase tracking-wider text-ink-faint">Note ·</span>{" "}
          This lane is isolated from Ask / Build: results are your own flashcards, <strong>not</strong>{" "}
          corpus-cited or source-verified.
        </div>
      </header>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          void run(question)
        }}
        className="flex flex-col gap-3"
      >
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder='e.g. "cavernous sinus contents"'
            className="flex-1 rounded-lg border border-navy-700/60 bg-navy-900/60 px-4 py-3 text-ink placeholder:text-ink-faint focus:border-teal/60 focus:outline-none"
            disabled={loading}
            autoFocus
          />
          <button
            type="submit"
            disabled={loading || !question.trim()}
            className="rounded-lg bg-teal px-5 py-3 font-medium text-navy-950 transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? "Searching…" : "Search"}
          </button>
        </div>
        <label className="flex items-center gap-3 text-sm text-ink-dim">
          Cards to show
          <input
            type="range"
            min={3}
            max={20}
            value={k}
            onChange={(e) => setK(Number(e.target.value))}
            disabled={loading}
            className="accent-teal"
          />
          <span className="font-mono text-ink">{k}</span>
        </label>
      </form>

      {!submitted && !loading && (
        <div className="flex flex-wrap gap-2">
          {HINTS.map((h) => (
            <button
              key={h}
              onClick={() => void run(h)}
              className="rounded-full border border-navy-700/60 bg-navy-900/40 px-3 py-1.5 font-mono text-xs text-ink-dim transition-colors hover:border-teal/50 hover:text-ink"
            >
              {h}
            </button>
          ))}
        </div>
      )}

      {loading && (
        <PipelineLoader steps={CARDS_STEPS} bars={4} estimate="Usually 10–40 seconds." />
      )}

      {netError && !loading && (
        <div className="rounded-lg border border-signal/40 bg-signal/10 p-5 text-sm">
          <p className="font-medium text-signal">Request failed</p>
          <p className="mt-1 text-ink-dim">{netError}</p>
          <p className="mt-2 font-mono text-xs text-ink-faint">
            Is the engine wrapper running on :8001?
          </p>
        </div>
      )}

      {resp && !loading && <CardsResult resp={resp} />}
    </div>
  )
}

function CardsResult({ resp }: { resp: CardsResponse }) {
  if (resp.kind === "error") {
    return (
      <div className="rounded-lg border border-signal/40 bg-signal/10 p-5 text-sm">
        <p className="font-medium text-signal">Engine error</p>
        <p className="mt-1 font-mono text-xs text-ink-dim">{resp.error}</p>
      </div>
    )
  }
  if (resp.kind === "unavailable") {
    return (
      <div className="rounded-lg border border-amber-400/40 bg-amber-400/10 p-5 text-sm">
        <p className="font-medium text-amber-300">Temporarily unavailable</p>
        <p className="mt-1 text-ink-dim">{resp.reason}</p>
      </div>
    )
  }
  if (resp.kind === "not_built") {
    return (
      <div className="rounded-lg border border-amber-400/40 bg-amber-400/10 p-5 text-sm">
        <p className="font-medium text-amber-300">Card bank not built</p>
        <p className="mt-1 whitespace-pre-wrap font-mono text-xs text-ink-dim">{resp.reason}</p>
      </div>
    )
  }
  if (!resp.cards.length) {
    return (
      <div className="rounded-lg border border-navy-700/60 bg-navy-900/40 p-5 text-sm text-ink-dim">
        No matching cards.
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-4">
      {resp.cards.map((c, i) => (
        <CardItem key={c.id || i} card={c} index={i} />
      ))}
    </div>
  )
}
