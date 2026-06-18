import { useEffect, useRef, useState } from "react"
import { askQuestion, type AskResponse } from "@/lib/api"
import AskLoader from "@/components/ask/AskLoader"
import AnswerView from "@/components/ask/AnswerView"
import FigureGrid from "@/components/ask/FigureGrid"
import SourcesList from "@/components/ask/SourcesList"
import LiteratureBlock from "@/components/ask/LiteratureBlock"

const HINTS = [
  "borders of the cavernous sinus",
  "blood supply of the lateral medulla",
  "Wallenberg syndrome findings",
  "watershed infarct territories",
]

export default function Ask() {
  const [question, setQuestion] = useState("")
  const [submitted, setSubmitted] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [resp, setResp] = useState<AskResponse | null>(null)
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
      const r = await askQuestion(text, ctrl.signal)
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
        <p className="font-mono text-xs uppercase tracking-[0.3em] text-teal">
          Ask · Citation-grounded
        </p>
        <h1 className="mt-2 font-display text-4xl font-bold tracking-tight text-ink">
          Ask the corpus
        </h1>
        <p className="mt-2 max-w-2xl text-ink-dim">
          Cited answers from your neurosurgery textbooks, augmented with contemporary PubMed
          literature. Decision-support only — verify against primary sources.
        </p>
      </header>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          void run(question)
        }}
        className="flex flex-col gap-3 sm:flex-row"
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder='e.g. "blood supply of the lateral medulla"'
          className="flex-1 rounded-lg border border-navy-700/60 bg-navy-900/60 px-4 py-3 text-ink placeholder:text-ink-faint focus:border-teal/60 focus:outline-none"
          disabled={loading}
          autoFocus
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="rounded-lg bg-teal px-5 py-3 font-medium text-navy-950 transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? "Asking…" : "Ask"}
        </button>
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

      {loading && <AskLoader />}

      {netError && !loading && (
        <div className="rounded-lg border border-signal/40 bg-signal/10 p-5 text-sm">
          <p className="font-medium text-signal">Request failed</p>
          <p className="mt-1 text-ink-dim">{netError}</p>
          <p className="mt-2 font-mono text-xs text-ink-faint">
            Is the engine wrapper running on :8001?
          </p>
        </div>
      )}

      {resp && !loading && <ResultView resp={resp} onPickVariant={(q) => void run(q)} />}
    </div>
  )
}

function ResultView({
  resp,
  onPickVariant,
}: {
  resp: AskResponse
  onPickVariant: (q: string) => void
}) {
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
        <p className="mt-2 font-mono text-xs text-ink-faint">Try again in a moment.</p>
      </div>
    )
  }

  if (resp.kind === "clarification") {
    return (
      <div className="rounded-xl border border-navy-700/60 bg-navy-900/50 p-6">
        <p className="font-medium text-ink">This question maps to several distinct topics.</p>
        <p className="mt-1 text-sm text-ink-dim">Pick the variant you meant:</p>
        <div className="mt-4 flex flex-col gap-2">
          {resp.variants.map((v) => (
            <button
              key={v.label}
              onClick={() => onPickVariant(v.rewrite || v.label)}
              className="rounded-lg border border-navy-700/60 bg-navy-850/60 px-4 py-3 text-left text-sm text-ink transition-colors hover:border-teal/50"
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>
    )
  }

  // kind === "answer"
  return (
    <div className="flex flex-col gap-6">
      <AnswerView text={resp.answer} />
      <FigureGrid figures={resp.figures} />
      <SourcesList citations={resp.citations} />
      {resp.literature && <LiteratureBlock literature={resp.literature} />}
    </div>
  )
}
