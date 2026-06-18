import { useEffect, useRef, useState } from "react"
import { buildDossier, fetchBuildPdf, type BuildResponse } from "@/lib/api"
import PipelineLoader from "@/components/PipelineLoader"
import EvidenceBar from "@/components/build/EvidenceBar"
import DossierView from "@/components/build/DossierView"

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

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="font-mono text-xs uppercase tracking-[0.3em] text-teal">
          Build · Pre-op dossier
        </p>
        <h1 className="mt-2 font-display text-4xl font-bold tracking-tight text-ink">
          Build a pre-op board
        </h1>
        <p className="mt-2 max-w-2xl text-ink-dim">
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
            className="flex-1 rounded-lg border border-navy-700/60 bg-navy-900/60 px-4 py-3 text-ink placeholder:text-ink-faint focus:border-teal/60 focus:outline-none"
            disabled={loading}
            autoFocus
          />
          <button
            type="submit"
            disabled={loading || !topic.trim()}
            className="rounded-lg bg-teal px-5 py-3 font-medium text-navy-950 transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? "Building…" : "Build board"}
          </button>
        </div>
        <div className="flex flex-wrap gap-5 text-sm text-ink-dim">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={enrich}
              onChange={(e) => setEnrich(e.target.checked)}
              disabled={loading}
              className="accent-teal"
            />
            Corpus enrichment
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={useLlm}
              onChange={(e) => setUseLlm(e.target.checked)}
              disabled={loading}
              className="accent-teal"
            />
            LLM explorer
          </label>
        </div>
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
        <PipelineLoader
          steps={BUILD_STEPS}
          bars={7}
          estimate="Usually 1–4 minutes — a full pre-op dossier is a lot of retrieval."
        />
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

      {resp && !loading && resp.kind === "error" && (
        <div className="rounded-lg border border-signal/40 bg-signal/10 p-5 text-sm">
          <p className="font-medium text-signal">Engine error</p>
          <p className="mt-1 font-mono text-xs text-ink-dim">{resp.error}</p>
        </div>
      )}

      {resp && !loading && resp.kind === "unavailable" && (
        <div className="rounded-lg border border-amber-400/40 bg-amber-400/10 p-5 text-sm">
          <p className="font-medium text-amber-300">Temporarily unavailable</p>
          <p className="mt-1 text-ink-dim">{resp.reason}</p>
        </div>
      )}

      {resp && !loading && resp.kind === "dossier" && (
        <div className="flex flex-col gap-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-2xl font-bold text-ink">{resp.dossier.title}</h2>
            <div className="flex flex-col items-end">
              <button
                onClick={() => void onDownloadPdf()}
                disabled={pdfLoading}
                className="rounded-lg border border-teal/50 px-4 py-2 text-sm font-medium text-teal transition-colors hover:bg-teal/10 disabled:opacity-50"
              >
                {pdfLoading ? "Rendering PDF…" : "Download PDF"}
              </button>
              {pdfError && <span className="mt-1 text-xs text-signal">{pdfError}</span>}
            </div>
          </div>
          <EvidenceBar summary={resp.dossier.summary} />
          <DossierView dossier={resp.dossier} />
        </div>
      )}
    </div>
  )
}
