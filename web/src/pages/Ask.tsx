import { useEffect, useRef, useState } from "react"
import { askQuestion, type AskResponse } from "@/lib/api"
import { Button, Card, Eyebrow } from "@/components/ui"
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
        <Eyebrow accent>Ask · Citation-grounded</Eyebrow>
        <h1 className="mt-3 font-display text-4xl font-bold tracking-tight text-foreground">
          Ask the corpus
        </h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
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
          className="field flex-1"
          disabled={loading}
          autoFocus
        />
        <Button type="submit" disabled={loading || !question.trim()} className="sm:px-7 sm:py-3">
          {loading ? "Asking…" : "Ask"}
        </Button>
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

      {loading && <AskLoader />}

      {netError && !loading && (
        <Card className="p-5 text-sm">
          <p className="font-bold text-primary">Request failed</p>
          <p className="mt-1 text-muted-foreground">{netError}</p>
          <p className="mt-2 font-mono text-xs text-muted-foreground">
            Is the engine wrapper running on :8001?
          </p>
        </Card>
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
        <p className="mt-2 font-mono text-xs text-muted-foreground">Try again in a moment.</p>
      </Card>
    )
  }

  if (resp.kind === "clarification") {
    return (
      <Card className="p-6">
        <p className="font-medium text-foreground">This question maps to several distinct topics.</p>
        <p className="mt-1 text-sm text-muted-foreground">Pick the variant you meant:</p>
        <div className="mt-4 flex flex-col gap-2">
          {resp.variants.map((v) => (
            <button
              key={v.label}
              onClick={() => onPickVariant(v.rewrite || v.label)}
              className="rounded-lg border border-border bg-muted px-4 py-3 text-left text-sm text-foreground transition-colors hover:border-primary"
            >
              {v.label}
            </button>
          ))}
        </div>
      </Card>
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
