import { useEffect, useRef, useState } from "react"
import {
  buildBriefing,
  fetchBriefingPdf,
  submitFeedback,
  type BriefingResponse,
  type FeedbackItemIn,
  type DossierClaim,
} from "@/lib/api"
import { Button, Eyebrow, Card } from "@/components/ui"
import PipelineLoader from "@/components/PipelineLoader"
import OperativeBriefingView from "@/components/build/OperativeBriefingView"
import BriefingFigureGallery from "@/components/build/BriefingFigureGallery"
import BriefingReferences from "@/components/build/BriefingReferences"
import DossierView, { type ClaimMark, type ClaimFilter } from "@/components/build/DossierView"
import RememberedPanel from "@/components/build/RememberedPanel"

const HINTS = [
  "left retrosigmoid vestibular schwannoma",
  "C5-6 ACDF",
  "right carotid endarterectomy",
  "ruptured ACoA aneurysm clipping",
  "L4-5 TLIF for spondylolisthesis",
]

const BUILD_STEPS = [
  "Designing the case-specific question set…",
  "Retrieving grounded passages per section…",
  "Synthesizing the operative briefing (7 sections)…",
  "Selecting high-yield figures + resolving references…",
]

export default function Build() {
  const [topic, setTopic] = useState("")
  const [submitted, setSubmitted] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [resp, setResp] = useState<BriefingResponse | null>(null)
  const [netError, setNetError] = useState<string | null>(null)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [pdfError, setPdfError] = useState<string | null>(null)
  const ctrlRef = useRef<AbortController | null>(null)

  const [rehearsal, setRehearsal] = useState(false)
  const [marks, setMarks] = useState<FeedbackItemIn[]>([])
  const [remembered, setRemembered] = useState<number | null>(null)
  const [filterActive] = useState<ClaimFilter>("all")

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
    if (resp?.kind !== "briefing" || !marks.length) return
    setRemembered(null)
    const r = await submitFeedback(resp.topic, marks, { enrich: true, use_llm: true })
    if (r.kind === "dossier") {
      // The feedback lane rebuilds the dossier; fold it back into the briefing response so the
      // Evidence Audit reflects the updated board (the briefing prose is unchanged by marks).
      setResp({ ...resp, dossier: r.dossier })
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
    setRemembered(null)
    setMarks([])
    setLoading(true)
    try {
      const r = await buildBriefing(text, { enrich: true, use_llm: true }, ctrl.signal)
      if (!ctrl.signal.aborted) setResp(r)
    } catch (e) {
      const err = e as { name?: string; message?: string }
      if (err?.name !== "AbortError") setNetError(err?.message ?? String(e))
    } finally {
      if (!ctrl.signal.aborted) setLoading(false)
    }
  }

  async function onDownloadPdf() {
    if (resp?.kind !== "briefing" || pdfLoading) return
    setPdfLoading(true)
    setPdfError(null)
    try {
      const blob = await fetchBriefingPdf(resp.build_id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${resp.topic.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-operative-briefing.pdf`
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
        ? resp.kind === "briefing"
          ? `Operative briefing ready: ${resp.briefing.title}.`
          : resp.kind === "unavailable"
            ? "Engine temporarily unavailable."
            : "Engine error."
        : ""

  return (
    <div className="flex flex-col gap-6">
      <div aria-live="polite" className="sr-only">
        {liveMsg}
      </div>

      <header>
        <Eyebrow accent>Build · Operative briefing</Eyebrow>
        <h1 className="mt-3 font-display text-4xl font-bold tracking-tight text-foreground">Operative briefing</h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          A one-page, attending-level briefing for the exact case — pathology, management, technique, risks &amp;
          equipment — with a high-yield figure gallery and a grounded references page. Decision-support only; verify
          against primary sources.
        </p>
      </header>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          void run(topic)
        }}
        className="flex flex-col gap-3 sm:flex-row"
      >
        <input
          type="text"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder='e.g. "ruptured ACoA aneurysm clipping"'
          className="field flex-1"
          disabled={loading}
          autoFocus
        />
        <Button type="submit" disabled={loading || !topic.trim()} className="sm:px-7 sm:py-3">
          {loading ? "Building…" : "Build briefing"}
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

      {loading && (
        <PipelineLoader
          steps={BUILD_STEPS}
          bars={7}
          estimate="Usually 1–4 minutes — a full operative briefing is a lot of retrieval + synthesis."
        />
      )}

      {netError && !loading && (
        <Card className="p-5 text-sm">
          <p className="font-bold text-destructive">Request failed</p>
          <p className="mt-1 text-muted-foreground">{netError}</p>
          <p className="mt-2 font-mono text-xs text-muted-foreground">Is the engine wrapper running on :8001?</p>
        </Card>
      )}

      {resp && !loading && resp.kind === "error" && (
        <Card className="p-5 text-sm">
          <p className="font-bold text-destructive">Engine error</p>
          <p className="mt-1 font-mono text-xs text-muted-foreground">{resp.error}</p>
        </Card>
      )}

      {resp && !loading && resp.kind === "unavailable" && (
        <Card className="bg-muted p-5 text-sm">
          <p className="font-bold text-foreground">Temporarily unavailable</p>
          <p className="mt-1 text-muted-foreground">{resp.reason}</p>
        </Card>
      )}

      {resp && !loading && resp.kind === "briefing" && (
        <div className="flex flex-col gap-6">
          {/* Case header + export / rehearsal toggle */}
          <div className="flex flex-wrap items-start justify-between gap-3 rounded-2xl border border-border bg-card p-5">
            <div className="flex min-w-0 flex-col gap-2">
              <span className="w-fit rounded-full border border-secondary/30 bg-secondary/10 px-3 py-1 font-mono text-[10px] text-secondary">
                {resp.topic}
              </span>
              {resp.provenance.degraded && (
                <span className="font-mono text-[10px] text-amber">
                  degraded: {resp.provenance.reason || "partial evidence"}
                </span>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={() => void onDownloadPdf()}
                disabled={pdfLoading}
                className="rounded-lg border border-border px-4 py-2 font-mono text-xs text-muted-foreground disabled:opacity-50"
              >
                {pdfLoading ? "Rendering…" : "Export PDF"}
              </button>
              <Button onClick={() => setRehearsal(!rehearsal)}>{rehearsal ? "Exit Rehearsal" : "Rehearse"}</Button>
            </div>
          </div>
          {pdfError && <span className="text-xs text-destructive">{pdfError}</span>}

          {/* 1 — one-page operative briefing */}
          <OperativeBriefingView briefing={resp.briefing} />

          {/* 2 — high-yield figure gallery */}
          <BriefingFigureGallery figures={resp.figures} />

          {/* 3 — references / evidence */}
          <BriefingReferences references={resp.references} />

          {/* Rehearsal controls */}
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

          {/* 4 — expandable full evidence audit (the existing claim-card dossier, preserved) */}
          <details className="rounded-2xl border border-border bg-card p-5">
            <summary className="cursor-pointer font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-secondary">
              Evidence Audit · full claim-card dossier ({resp.dossier.sections.length} sections)
            </summary>
            <div className="mt-4">
              <DossierView
                dossier={resp.dossier}
                filter={filterActive}
                rehearsal={rehearsal}
                markOf={markOf}
                onMark={onMark}
                onMissing={onMissing}
              />
            </div>
          </details>
        </div>
      )}
    </div>
  )
}
