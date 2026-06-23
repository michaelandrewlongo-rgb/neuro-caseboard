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
import { EvidenceGauge } from "@/components/charts/EvidenceGauge"
import PlanningMetrics from "@/components/build/PlanningMetrics"
import DossierView, { type ClaimMark, type ClaimFilter } from "@/components/build/DossierView"
import RememberedPanel from "@/components/build/RememberedPanel"
import { subsetClaims } from "@/lib/claimFilter"
import { heroGridColumns, planningHasData } from "@/lib/heroPanels"

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
  const [filterActive, setFilterActive] = useState<ClaimFilter>("all")

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
      setFilterActive("all")
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
    setFilterActive("all")
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

  // Derived from resp when a dossier is ready; safe null-guard for pre-submit states.
  const dossSummary = resp?.kind === "dossier" ? resp.dossier.summary : null
  const claimTotal = dossSummary
    ? dossSummary.supported + dossSummary.to_verify + dossSummary.quarantined
    : 0
  // Post-dedup claims DossierView actually renders. compile.py runs dedup_sections AFTER the
  // summary is computed, so the rendered claim list is a subset of summary.* — the segmented-control
  // tab counts must equal what renders (NOT the card-level audit gauge, which stays on summary.*).
  const renderedClaims =
    resp?.kind === "dossier" ? resp.dossier.sections.flatMap((s) => s.claims) : []

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
          <p className="font-bold text-destructive">Request failed</p>
          <p className="mt-1 text-muted-foreground">{netError}</p>
          <p className="mt-2 font-mono text-xs text-muted-foreground">
            Is the engine wrapper running on :8001?
          </p>
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

      {resp && !loading && resp.kind === "dossier" && (
        <div className="flex flex-col gap-6">
          {/* ── Case header ── */}
          <div
            className="rounded-[16px] p-5"
            style={{
              background: "rgba(255,255,255,.022)",
              border: "1px solid rgba(255,255,255,.08)",
            }}
          >
            <p
              className="mb-2 font-mono text-[9px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "#6b93ff" }}
            >
              ACTIVE CASEBOARD · PRE-OP DOSSIER · v3
            </p>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex min-w-0 flex-col gap-2">
                <h2
                  className="font-display text-2xl font-bold leading-tight"
                  style={{ color: "#ededed" }}
                >
                  {resp.dossier.title}
                </h2>
                <div className="flex flex-wrap gap-2">
                  <span
                    className="font-mono text-[10px]"
                    style={{
                      padding: "3px 10px",
                      borderRadius: "999px",
                      background: "rgba(107,147,255,.12)",
                      color: "#6b93ff",
                      border: "1px solid rgba(107,147,255,.22)",
                    }}
                  >
                    {resp.topic}
                  </span>
                  <span
                    className="font-mono text-[10px]"
                    style={{
                      padding: "3px 10px",
                      borderRadius: "999px",
                      background: "rgba(255,255,255,.06)",
                      color: "#a8a8a8",
                      border: "1px solid rgba(255,255,255,.09)",
                    }}
                  >
                    PRE-OP
                  </span>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => void onDownloadPdf()}
                  disabled={pdfLoading}
                  className="font-mono text-[11px] transition-all"
                  style={{
                    padding: "7px 15px",
                    borderRadius: "9px",
                    background: "transparent",
                    color: pdfLoading ? "#666666" : "#a8a8a8",
                    border: "1px solid rgba(255,255,255,.15)",
                    cursor: pdfLoading ? "default" : "pointer",
                  }}
                >
                  {pdfLoading ? "Rendering…" : "Export PDF"}
                </button>
                <button
                  type="button"
                  onClick={() => setRehearsal(!rehearsal)}
                  className="font-mono text-[11px] font-bold transition-all"
                  style={{
                    padding: "7px 15px",
                    borderRadius: "9px",
                    background: rehearsal ? "rgba(255,255,255,.08)" : "#ededed",
                    color: rehearsal ? "#ededed" : "#0a0a0a",
                    border: rehearsal ? "1px solid rgba(255,255,255,.18)" : "none",
                    cursor: "pointer",
                    boxShadow: rehearsal ? "none" : "0 6px 22px rgba(0,0,0,.45)",
                  }}
                >
                  {rehearsal ? "Exit Rehearsal" : "Rehearse"}
                </button>
              </div>
            </div>
          </div>

          {/* PDF error */}
          {pdfError && (
            <span className="text-xs" style={{ color: "#ff5a5a" }}>
              {pdfError}
            </span>
          )}

          {/* Rehearsal: remember marks controls */}
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

          {/* Remembered panel */}
          {remembered !== null && <RememberedPanel remembered={remembered} />}

          {/* ── Telemetry grid — only panels backed by real engine data render ──
              Evidence Integrity always has data. Risk Topology and Planning
              Metrics hide when empty (no fabricated clinical numbers) and the
              grid reflows so collapsed panels leave no dead columns. Each panel
              reappears once a real engine field is wired into its gate below. */}
          {(() => {
            // Risk Topology has no BuildResponse field yet; gate it on a future
            // `resp.dossier.riskTopology`-style field. False today → block hidden.
            const showRisk = false
            // <PlanningMetrics /> is rendered below with no props today, so the
            // same emptiness check the panel uses returns false → block hidden.
            const showPlanning = planningHasData({})
            const visiblePanels = 1 + (showRisk ? 1 : 0) + (showPlanning ? 1 : 0)
            return (
          <div className="grid gap-4" style={{ gridTemplateColumns: heroGridColumns(visiblePanels) }}>
            {/* Risk topology — no backing data in BuildResponse; hidden until the engine populates it */}
            {showRisk && (
            <div
              className="flex flex-col gap-3 p-4"
              style={{
                background:
                  "linear-gradient(160deg, rgba(255,255,255,.05), rgba(255,255,255,.012))",
                border: "1px solid rgba(255,255,255,.09)",
                borderRadius: "16px",
              }}
            >
              <p
                className="font-mono text-[9px] font-bold uppercase tracking-[0.18em]"
                style={{ color: "#8a8a8a" }}
              >
                Risk Topology
              </p>
              <div className="flex flex-1 flex-col items-center justify-center gap-2 py-6 text-center">
                <span
                  className="font-mono text-[9px] font-bold uppercase tracking-[0.14em]"
                  style={{ color: "#666666" }}
                >
                  Not available
                </span>
                <p
                  className="max-w-[16ch] text-[11px] leading-relaxed"
                  style={{ color: "#8a8a8a" }}
                >
                  No risk-topology data from engine
                </p>
              </div>
            </div>
            )}

            {/* Evidence integrity — driven by real EvidenceSummary */}
            <div
              className="flex flex-col gap-3 p-4"
              style={{
                background:
                  "linear-gradient(160deg, rgba(255,255,255,.05), rgba(255,255,255,.012))",
                border: "1px solid rgba(255,255,255,.09)",
                borderRadius: "16px",
              }}
            >
              <p
                className="font-mono text-[9px] font-bold uppercase tracking-[0.18em]"
                style={{ color: "#6b93ff" }}
              >
                Evidence Integrity
              </p>
              <div className="flex flex-col items-center gap-4">
                <EvidenceGauge
                  size={140}
                  rings={[
                    {
                      r: 54,
                      frac: claimTotal > 0 ? resp.dossier.summary.supported / claimTotal : 0,
                      color: "#34e07f",
                      glow: "#34e07f",
                    },
                    {
                      r: 40,
                      frac: claimTotal > 0 ? resp.dossier.summary.to_verify / claimTotal : 0,
                      color: "#ffc94d",
                      glow: "#ffc94d",
                    },
                    {
                      r: 26,
                      frac: claimTotal > 0 ? resp.dossier.summary.quarantined / claimTotal : 0,
                      color: "#ff5a5a",
                      glow: "#ff5a5a",
                    },
                  ]}
                >
                  <div className="text-center">
                    <span
                      className="font-display text-2xl font-bold"
                      style={{ color: "#ededed" }}
                    >
                      {claimTotal}
                    </span>
                    <p
                      className="font-mono text-[8px] uppercase tracking-[0.18em]"
                      style={{ color: "#8a8a8a" }}
                    >
                      CLAIMS
                    </p>
                  </div>
                </EvidenceGauge>
                <div className="flex flex-col gap-1.5">
                  {[
                    {
                      color: "#34e07f",
                      label: "Supported",
                      count: resp.dossier.summary.supported,
                    },
                    {
                      color: "#ffc94d",
                      label: "Verify",
                      count: resp.dossier.summary.to_verify,
                    },
                    {
                      color: "#ff5a5a",
                      label: "Quarantine",
                      count: resp.dossier.summary.quarantined,
                    },
                  ].map(({ color, label, count }) => (
                    <div key={label} className="flex items-center gap-2">
                      <span
                        className="h-2 w-2 shrink-0 rounded-full"
                        aria-hidden="true"
                        style={{ background: color, boxShadow: `0 0 6px ${color}` }}
                      />
                      <span className="text-[11px]" style={{ color: "#a8a8a8" }}>
                        {label}{" "}
                        <span className="font-mono font-bold" style={{ color: "#ededed" }}>
                          {count}
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Planning metrics — hidden until the engine populates planning fields */}
            {showPlanning && <PlanningMetrics />}
          </div>
            )
          })()}

          {/* ── Evidence filter segmented control ── */}
          <div
            className="flex flex-wrap items-center gap-1 self-start p-1"
            style={{
              background: "rgba(255,255,255,.04)",
              border: "1px solid rgba(255,255,255,.08)",
              borderRadius: "11px",
            }}
            role="group"
            aria-label="Filter evidence by status"
          >
            {[
              { key: "all" as const, label: "ALL", count: renderedClaims.length },
              {
                key: "supported" as const,
                label: "SUPPORTED",
                count: subsetClaims(renderedClaims, "supported").length,
              },
              {
                key: "verify" as const,
                label: "VERIFY",
                count: subsetClaims(renderedClaims, "verify").length,
              },
              {
                key: "quarantine" as const,
                label: "QUARANTINE",
                count: subsetClaims(renderedClaims, "quarantine").length,
              },
            ].map(({ key, label, count }) => (
              <button
                key={key}
                type="button"
                onClick={() => setFilterActive(key)}
                aria-pressed={filterActive === key}
                className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] transition-all"
                style={{
                  padding: "5px 12px",
                  borderRadius: "8px",
                  background: filterActive === key ? "rgba(107,147,255,.18)" : "transparent",
                  color: filterActive === key ? "#6b93ff" : "#8a8a8a",
                  border: `1px solid ${filterActive === key ? "rgba(107,147,255,.35)" : "transparent"}`,
                  cursor: "pointer",
                }}
              >
                {label}{" "}
                <span
                  className="font-mono"
                  style={{ color: filterActive === key ? "#6b93ff" : "#666666" }}
                >
                  ({count})
                </span>
              </button>
            ))}
          </div>

          {/* ── Dossier body ── */}
          <DossierView
            dossier={resp.dossier}
            filter={filterActive}
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
