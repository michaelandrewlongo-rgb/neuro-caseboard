import { useEffect, useRef, useState } from "react"
import { startAsk, openAskStream } from "@/lib/api"
import {
  applyAskEvent,
  emptyAskState,
  loadAsk,
  saveAsk,
  clearAsk,
  type AskState,
  type AskEvent,
} from "@/lib/askStore"
import { Button, Card, Eyebrow } from "@/components/ui"
import AskLoader from "@/components/ask/AskLoader"
import AnswerView from "@/components/ask/AnswerView"
import FigureGrid from "@/components/ask/FigureGrid"
import SourcesList from "@/components/ask/SourcesList"
import LiteratureBlock from "@/components/ask/LiteratureBlock"
import { CitationAudit } from "@/components/ask/CitationAudit"
import { auditSummaryLabel } from "@/lib/askLayout"

const HINTS = [
  "borders of the cavernous sinus",
  "blood supply of the lateral medulla",
  "Wallenberg syndrome findings",
  "watershed infarct territories",
  "anterior communicating artery perforators",
  "Spetzler-Martin AVM grading",
]

// Events after which the stream is finished and the EventSource must be closed (it would
// otherwise auto-reconnect on the server closing the connection).
const TERMINAL = new Set<AskEvent["type"]>(["done"])

export default function Ask() {
  const esRef = useRef<EventSource | null>(null)
  // Authoritative state for the SSE closure: updated synchronously on every event so rapidly
  // arriving tokens always reduce from the freshest state (setState alone is async → stale).
  const stateRef = useRef<AskState | null>(null)
  // Restore the last job in the initializer (not an effect) so the very first render already
  // shows the persisted answer/progress. The `state` initializer runs before `question`'s, so
  // stateRef is populated by the time we read it below.
  const [state, setState] = useState<AskState | null>(() => {
    const saved = loadAsk(localStorage)
    if (saved) stateRef.current = saved
    return saved
  })
  const [question, setQuestion] = useState(() => stateRef.current?.question ?? "")
  const [netError, setNetError] = useState<string | null>(null)

  // If a restored job was still streaming, reconnect at its cursor (pure subscription setup;
  // the connect's onEvent callback updates state, which is the allowed pattern).
  useEffect(() => {
    const saved = stateRef.current
    if (saved && !saved.done) connect(saved.jobId, saved.nextIndex)
    return () => esRef.current?.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function connect(jobId: string, cursor: number) {
    esRef.current?.close()
    const es = openAskStream(jobId, cursor, {
      onEvent: (ev: AskEvent, index: number) => {
        const prev = stateRef.current ?? emptyAskState(question, jobId)
        const next = applyAskEvent(prev, ev, index)
        stateRef.current = next // sync update before the async setState
        setState(next)
        saveAsk(localStorage, next)
        if (next.done || TERMINAL.has(ev.type)) es.close()
      },
      // EventSource auto-retries on a transport drop; progress is already persisted.
      onError: () => {},
    })
    esRef.current = es
  }

  async function run(q: string, opts?: { skipDisambiguation?: boolean }) {
    const text = q.trim()
    if (!text) return
    esRef.current?.close()
    clearAsk(localStorage)
    setQuestion(text)
    setNetError(null)
    try {
      const { job_id } = await startAsk(text, opts?.skipDisambiguation ?? false)
      const fresh = emptyAskState(text, job_id)
      stateRef.current = fresh
      setState(fresh)
      saveAsk(localStorage, fresh)
      connect(job_id, 0)
    } catch (e) {
      const err = e as { message?: string }
      setNetError(err?.message ?? String(e))
    }
  }

  // Show the slow-call loader only until the first content (sources / figures / tokens) arrives.
  const streaming = !!state && !state.done && state.status === "streaming"
  const noContentYet =
    !state || (!state.answer && state.sources.length === 0 && state.figures.length === 0)
  const showLoader = streaming && noContentYet
  const submitted = !!state || !!netError

  const liveMsg = streaming
    ? ""
    : netError
      ? "Request failed."
      : state?.status === "answer"
        ? "Answer ready below."
        : state?.status === "clarification"
          ? "This question maps to several topics — choose one below."
          : state?.status === "unavailable"
            ? "Engine temporarily unavailable."
            : state?.status === "error"
              ? "Engine error."
              : ""

  return (
    <div className="flex flex-col gap-6">
      {/* Persistent live region: announces result arrival to screen readers after a slow call. */}
      <div aria-live="polite" className="sr-only">
        {liveMsg}
      </div>
      <header>
        <Eyebrow accent>ASK · CITED ANSWER ENGINE</Eyebrow>
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
          disabled={streaming}
          autoFocus
        />
        <Button type="submit" disabled={streaming || !question.trim()} className="sm:px-7 sm:py-3">
          {streaming ? "Asking…" : "Ask"}
        </Button>
      </form>

      {!submitted && (
        <div className="flex flex-wrap gap-2">
          {HINTS.map((h) => (
            <button key={h} onClick={() => void run(h)} className="chip">
              {h}
            </button>
          ))}
        </div>
      )}

      {showLoader && <AskLoader />}

      {netError && (
        <Card className="p-5 text-sm">
          <p className="font-bold text-destructive">Request failed</p>
          <p className="mt-1 text-muted-foreground">{netError}</p>
          <p className="mt-2 font-mono text-xs text-muted-foreground">
            Is the engine wrapper running on :8001?
          </p>
        </Card>
      )}

      {state && !netError && (
        <ResultView
          state={state}
          onPickVariant={(q) => void run(q, { skipDisambiguation: true })}
        />
      )}
    </div>
  )
}

function ResultView({
  state,
  onPickVariant,
}: {
  state: AskState
  onPickVariant: (q: string) => void
}) {
  if (state.status === "error") {
    return (
      <Card className="p-5 text-sm">
        <p className="font-bold text-destructive">Engine error</p>
        <p className="mt-1 font-mono text-xs text-muted-foreground">{state.reason}</p>
      </Card>
    )
  }

  if (state.status === "unavailable") {
    return (
      <Card className="bg-muted p-5 text-sm">
        <p className="font-bold text-foreground">Temporarily unavailable</p>
        <p className="mt-1 text-muted-foreground">{state.reason}</p>
        <p className="mt-2 font-mono text-xs text-muted-foreground">Try again in a moment.</p>
      </Card>
    )
  }

  if (state.status === "clarification") {
    return (
      <Card className="p-6">
        <p className="font-medium text-foreground">This question maps to several distinct topics.</p>
        <p className="mt-1 text-sm text-muted-foreground">Pick the variant you meant:</p>
        <div className="mt-4 flex flex-col gap-2">
          {state.variants.map((v) => (
            <button
              key={v.label}
              onClick={() => onPickVariant(v.rewrite || v.label)}
              className="border-2 border-border bg-muted px-4 py-3 text-left text-sm text-foreground transition-colors hover:border-primary"
            >
              {v.label}
            </button>
          ))}
        </div>
      </Card>
    )
  }

  // Streaming or completed answer — render each piece as soon as it exists. The Citation Audit
  // is secondary (it restates counts the sources already carry), so it stays collapsed below and
  // only once the answer is final.
  return (
    <div className="flex flex-col gap-6">
      {state.answer && <AnswerView text={state.answer} />}
      {state.figures.length > 0 && <FigureGrid figures={state.figures} />}
      {state.sources.length > 0 && <SourcesList citations={state.sources} />}
      {state.literature && <LiteratureBlock literature={state.literature} />}
      {state.status === "answer" && (
        <details className="surface p-4">
          <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
            {auditSummaryLabel(state.sources.length, state.literature?.citations.length ?? 0)}
          </summary>
          <div className="mt-4 sm:max-w-md">
            <CitationAudit citations={state.sources} literature={state.literature} />
          </div>
        </details>
      )}
    </div>
  )
}
