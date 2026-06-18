import { useEffect, useRef, useState } from "react"
import { searchCards, type CardsResponse } from "@/lib/api"
import { Button, Card, Eyebrow } from "@/components/ui"
import PipelineLoader from "@/components/PipelineLoader"
import CardItem from "@/components/cards/CardItem"

const HINTS = ["cavernous sinus contents", "Meckel cave", "spinal cord tracts", "circle of Willis"]

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
        <Eyebrow accent>Cards · Study deck</Eyebrow>
        <h1 className="mt-3 font-display text-4xl font-bold tracking-tight text-foreground">
          Board-review card bank
        </h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          Hybrid search over your personal ABNS / SANS deck — your own study notes, matched but not
          synthesized.
        </p>
        <Card className="mt-3 px-4 py-3 text-sm text-muted-foreground">
          <span className="font-mono text-xs uppercase tracking-wider text-muted-foreground">Note ·</span>{" "}
          This lane is isolated from Ask / Build: results are your own flashcards, <strong>not</strong>{" "}
          corpus-cited or source-verified.
        </Card>
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
            className="field flex-1"
            disabled={loading}
            autoFocus
          />
          <Button type="submit" disabled={loading || !question.trim()} className="sm:px-7 sm:py-3">
            {loading ? "Searching…" : "Search"}
          </Button>
        </div>
        <label className="flex items-center gap-3 text-sm text-muted-foreground">
          Cards to show
          <input
            type="range"
            min={3}
            max={20}
            value={k}
            onChange={(e) => setK(Number(e.target.value))}
            disabled={loading}
            className="accent-primary"
          />
          <span className="tnum font-mono text-foreground">{k}</span>
        </label>
      </form>

      {!submitted && !loading && (
        <div className="flex flex-wrap gap-2">
          {HINTS.map((h) => (
            <button key={h} onClick={() => void run(h)} className="chip">
              {h}
            </button>
          ))}
        </div>
      )}

      {loading && (
        <PipelineLoader steps={CARDS_STEPS} bars={4} estimate="Usually 10–40 seconds." />
      )}

      {netError && !loading && (
        <Card className="p-5 text-sm">
          <p className="font-bold text-primary">Request failed</p>
          <p className="mt-1 text-muted-foreground">{netError}</p>
          <p className="mt-2 font-mono text-xs text-muted-foreground">
            Is the engine wrapper running on :8001?
          </p>
        </Card>
      )}

      {resp && !loading && <CardsResult resp={resp} />}
    </div>
  )
}

function CardsResult({ resp }: { resp: CardsResponse }) {
  if (resp.kind === "error") {
    return (
      <Card className="p-5 text-sm">
        <p className="font-bold text-primary">Engine error</p>
        <p className="mt-1 font-mono text-xs text-muted-foreground">{resp.error}</p>
      </Card>
    )
  }
  if (resp.kind === "unavailable") {
    return (
      <Card className="bg-secondary p-5 text-sm">
        <p className="font-bold text-foreground">Temporarily unavailable</p>
        <p className="mt-1 text-muted-foreground">{resp.reason}</p>
      </Card>
    )
  }
  if (resp.kind === "not_built") {
    return (
      <Card className="bg-secondary p-5 text-sm">
        <p className="font-bold text-foreground">Card bank not built</p>
        <p className="mt-1 whitespace-pre-wrap font-mono text-xs text-muted-foreground">{resp.reason}</p>
      </Card>
    )
  }
  if (!resp.cards.length) {
    return <Card className="p-5 text-sm text-muted-foreground">No matching cards.</Card>
  }
  return (
    <div className="flex flex-col gap-4">
      {resp.cards.map((c, i) => (
        <CardItem key={c.id || i} card={c} index={i} />
      ))}
    </div>
  )
}
