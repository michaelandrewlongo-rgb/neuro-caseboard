import { useEffect, useRef, useState } from "react"
import {
  buildDossier,
  fetchBuildPdf,
  submitFeedback,
  type BuildResponse,
  type FeedbackItemIn,
  type DossierClaim,
} from "@/lib/api"
import { Button, Card, Eyebrow } from "@/components/ui"
import PipelineLoader from "@/components/PipelineLoader"
import EvidenceBar from "@/components/build/EvidenceBar"
import DossierView, { type ClaimMark } from "@/components/build/DossierView"
import RememberedPanel from "@/components/build/RememberedPanel"

const HINTS = [
  "left retrosigmoid vestibular schwannoma",
  "C5-6 ACDF",
  "right carotid endarterectomy",
  "awake left temporal glioma",
]

const BUILD_STEPS = [
  "Designing the case-specific question set · Vertex…",
  "Retrieving grounded passages per card…",
  "Auditing evidence · supported / verify / quarantine…",
  "Attaching textbook figures…",
]

export default function Build() {
  const [topic, setTopic] = useState("")
  const [submitted, setSubmitted] = useState<string | null>(null)
  const [enrich, setEnrich] = useState(true)
  const [useLlm, setUseLlm] = useState(true)
  const [loading, setLoading] = useState(false)
  const [resp, setResp] = useState<BuildResponse | null>(null)
  const [netError, setNetError] = useState<string | null>(null)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [pdfError, setPdfError] = useState<string | null>(null)
  const ctrlRef = useRef<AbortController | null>(null)

  const [rehearsal, setRehearsal] = useState(false)
  const [marks, setMarks] = useState<FeedbackItemIn[]>([])
  const [remembered, setRemembered] = useState<number | null>(null)

  const onMark = (heading: string, claim: DossierClaim, mark: ClaimMark) =>
    setMarks((prev) => {
      const isClaim = (x: FeedbackItemIn) =>
        x.section === heading && x.text === claim.text && (x.mark === "wrong" || x.mark === "important")
      const without = prev.filter((x) => !isClaim(x))
      const had = prev.some((x) => isClaim(x) && x.mark === mark)
      return had ? without : [...without, { mark, text: claim.text, section: heading }]
    })
  const markOf = (heading: string, claim: DossierClaim): ClaimMark | null => {
    const m = marks.find(
      (x) => x.section === heading && x.text === claim.text && (x.mark === "wrong" || x.mark === "important"),
    )
    return (m?.mark as ClaimMark) ?? null
  }
  const onMissing = (heading: string, text: string) =>
    setMarks((prev) => [...prev, { mark: "missing", text, section: heading }])

  async function remember() {
    if (resp?.kind !== "dossier" || !marks.length) return
    setRemembered(null)
    const r = await submitFeedback(resp.topic, marks, { enrich, use_llm: useLlm })
    if (r.kind === "dossier") {
      // Use the rebuilt board's own build_id so Download PDF exports THIS board, not the pre-feedback one.
      setResp({ kind: "dossier", build_id: r.build_id, topic: r.topic, dossier: r.dossier })
      setRemembered(r.remembered)
      setMarks([])
    } else {
      setNetError(r.kind === "unavailable" ? r.reason : r.error)
    }
  }

  useEffect(() => () => ctrlRef.current?.abort(), [])

  async function run(t: string) {
    const text = t.trim()
    if (!text || loading) return
    ctrlRef.current?.abort()
    const ctrl = new AbortController()
    ctrlRef.current = ctrl
    setSubmitted(text)
    setTopic(text)
    setResp(null)
    setNetError(null)
    setPdfError(null)
    setLoading(true)
    try {
      const r = await buildDossier(text, { enrich, use_llm: useLlm }, ctrl.signal)
      if (!ctrl.signal.aborted) setResp(r)
    } catch (e) {
      const err = e as { name?: string; message?: string }
      if (err?.name !== "AbortError") setNetError(err?.message ?? String(e))
    } finally {
      if (!ctrl.signal.aborted) setLoading(false)
    }
  }

  async function onDownloadPdf() {
    if (resp?.kind !== "dossier" || pdfLoading) return
    setPdfLoading(true)
    setPdfError(null)
    try {
      const blob = await fetchBuildPdf(resp.build_id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${resp.topic.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-caseboard.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      setPdfError((e as Error).message)
    } finally {
      setPdfLoading(false)
    }
  }

  const liveMsg = loading
    ? ""
    : netError
      ? "Request failed."
      : resp
        ? resp.kind === "dossier"
          ? `Dossier ready: ${resp.dossier.title}.`
          : resp.kind === "unavailable"
            ? "Engine temporarily unavailable."
            : "Engine error."
        : ""

  return (
    <div className="flex flex-col gap-6">
      {/* Persistent live region: announces dossier completion to screen readers after a slow call. */}
      <div aria-live="polite" className="sr-only">
        {liveMsg}
      </div>
      <header>
        <Eyebrow accent>Build · Pre-op dossier</Eyebrow>
        <h1 className="mt-3 font-display text-4xl font-bold tracking-tight text-foreground">
          Build a pre-op board
        </h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          A structured, corpus-grounded dossier for the exact procedure — anatomy at risk, operative
          plan, risk &amp; rescue. Decision-support only; verify against primary sources.
        </p>
      </header>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          void run(topic)
        }}
        className="flex flex-col gap-3"
      >
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder='e.g. "right carotid endarterectomy"'
            className="field flex-1"
            disabled={loading}
            autoFocus
          />
          <Button type="submit" disabled={loading || !topic.trim()} className="sm:px-7 sm:py-3">
            {loading ? "Building…" : "Build board"}
          </Button>
        </div>
        <div className="flex flex-wrap gap-5 text-sm text-muted-foreground">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={enrich}
              onChange={(e) => setEnrich(e.target.checked)}
              disabled={loading}
              className="accent-primary"
            />
            Corpus enrichment
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={useLlm}
              onChange={(e) => setUseLlm(e.target.checked)}
              disabled={loading}
              className="accent-primary"
            />
            LLM explorer
          </label>
        </div>
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
        <PipelineLoader
          steps={BUILD_STEPS}
          bars={7}
          estimate="Usually 1–4 minutes — a full pre-op dossier is a lot of retrieval."
        />
      )}

      {netError && !loading && (
        <Card className="p-5 text-sm">
          <p className="font-bold text-primary-ink">Request failed</p>
          <p className="mt-1 text-muted-foreground">{netError}</p>
          <p className="mt-2 font-mono text-xs text-muted-foreground">
            Is the engine wrapper running on :8001?
          </p>
        </Card>
      )}

      {resp && !loading && resp.kind === "error" && (
        <Card className="p-5 text-sm">
          <p className="font-bold text-primary-ink">Engine error</p>
          <p className="mt-1 font-mono text-xs text-muted-foreground">{resp.error}</p>
        </Card>
      )}

      {resp && !loading && resp.kind === "unavailable" && (
        <Card className="bg-secondary p-5 text-sm">
          <p className="font-bold text-foreground">Temporarily unavailable</p>
          <p className="mt-1 text-muted-foreground">{resp.reason}</p>
        </Card>
      )}

      {resp && !loading && resp.kind === "dossier" && (
        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-2xl font-bold text-foreground">{resp.dossier.title}</h2>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input
                  type="checkbox"
                  checked={rehearsal}
                  onChange={(e) => setRehearsal(e.target.checked)}
                  className="accent-primary"
                />
                Rehearsal mode
              </label>
              <Button variant="outline" onClick={() => void onDownloadPdf()} disabled={pdfLoading}>
                {pdfLoading ? "Rendering PDF…" : "Download PDF"}
              </Button>
            </div>
          </div>
          {pdfError && <span className="text-xs text-destructive">{pdfError}</span>}
          {rehearsal && (
            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={() => void remember()} disabled={!marks.length}>
                Remember {marks.length || ""} mark{marks.length === 1 ? "" : "s"} &amp; update board
              </Button>
              <span className="text-xs text-muted-foreground">
                Mark claims ✗ wrong / ★ important, or add a missing consideration per section.
              </span>
            </div>
          )}
          {remembered !== null && <RememberedPanel remembered={remembered} />}
          <EvidenceBar summary={resp.dossier.summary} />
          <DossierView
            dossier={resp.dossier}
            rehearsal={rehearsal}
            markOf={markOf}
            onMark={onMark}
            onMissing={onMissing}
          />
        </div>
      )}
    </div>
  )
}
