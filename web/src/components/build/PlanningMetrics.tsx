/**
 * PlanningMetrics — Dossier telemetry panel (Task 4b).
 * Task 5: Keyboard-accessible provenance popovers added (data-gated).
 *
 * HONEST DATA MAPPING (clinical tool — binding):
 * BuildResponse carries NO backing fields for these clinical percentages or
 * timing estimates. Props are typed for future engine support, but until the
 * engine exposes planning fields all values are absent and the panel renders
 * an honest "no planning data from engine" state.
 * Do NOT pass fabricated numbers.
 *
 * PROVENANCE (Task 5 — forward-compatible scaffolding, currently dormant):
 * Each metric accepts an optional `provenance` field. The popover renders ONLY
 * when that field is present. When absent (the current real state with no engine
 * data), NO tooltip renders and NO derivation text is fabricated.
 */

import { useCallback, useId, useRef, useState } from "react"
import { cn } from "../../lib/utils"

/** Per-metric provenance data. Forward-compatible scaffolding — no engine fields emit this yet. */
export interface Provenance {
  /** One sentence describing how the metric was derived. */
  derivation: string
  /** Source chips shown below the derivation (e.g. "[n]", "n≈1006", "9–14%"). */
  sources: string[]
}

/** Returns true when the user prefers reduced motion. Checked once at mount. */
function useReducedMotion(): boolean {
  const [reduced] = useState<boolean>(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  )
  return reduced
}

// ---------------------------------------------------------------------------
// ProvenancePopover — reusable hover + focus popover trigger
// ---------------------------------------------------------------------------

interface ProvenancePopoverProps {
  label: string
  labelColor: string
  provenance: Provenance
  reducedMotion: boolean
}

function ProvenancePopover({
  label,
  labelColor,
  provenance,
  reducedMotion,
}: ProvenancePopoverProps) {
  const [open, setOpen] = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)
  const tooltipId = useId()

  const show = useCallback(() => setOpen(true), [])
  const hide = useCallback(() => setOpen(false), [])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLButtonElement>) => {
      if (e.key === "Escape") {
        setOpen(false)
        btnRef.current?.blur()
      }
    },
    [],
  )

  return (
    <div className="relative inline-block">
      <button
        ref={btnRef}
        type="button"
        className={cn(
          "cursor-help border-0 bg-transparent p-0 text-left",
          "focus-visible:outline-none",
          /* visible focus ring using the ring token */
          "focus-visible:ring-1 focus-visible:ring-[var(--color-ring)] focus-visible:rounded-sm",
        )}
        style={{
          /* dotted underline signals tooltip affordance */
          textDecoration: "underline dotted",
          textDecorationColor: `${labelColor}66`,
          textUnderlineOffset: "2px",
        }}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        onKeyDown={handleKeyDown}
        aria-describedby={open ? tooltipId : undefined}
        aria-expanded={open}
        aria-label={`${label} — show derivation`}
      >
        <span
          className="font-mono text-[9px] font-bold uppercase tracking-[0.14em]"
          style={{ color: labelColor }}
        >
          {label}
        </span>
      </button>

      {/* Glass popover — pointer-events-none so it never traps focus */}
      <div
        id={tooltipId}
        role="tooltip"
        aria-hidden={!open}
        className="pointer-events-none absolute bottom-[calc(100%+8px)] left-0 z-50 w-56"
        style={{
          opacity: open ? 1 : 0,
          transition: reducedMotion ? "none" : "opacity .16s ease",
          visibility: open ? "visible" : "hidden",
        }}
      >
        <div
          className="p-3"
          style={{
            background: "rgba(10,10,10,.97)",
            border: "1px solid rgba(255,255,255,.13)",
            borderRadius: "11px",
            backdropFilter: "blur(14px)",
          }}
        >
          {/* DERIVATION mono eyebrow */}
          <p
            className="mb-1.5 font-mono text-[9px] font-bold uppercase tracking-[0.18em]"
            style={{ color: "#6b93ff" }}
          >
            Derivation
          </p>

          {/* Derivation sentence */}
          <p className="mb-2 text-[11px] leading-relaxed" style={{ color: "#ededed" }}>
            {provenance.derivation}
          </p>

          {/* Source chips */}
          {provenance.sources.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {provenance.sources.map((src, idx) => (
                <span
                  key={idx}
                  className="font-mono text-[9px]"
                  style={{
                    background: "rgba(107,147,255,.12)",
                    color: "#6b93ff",
                    border: "1px solid rgba(107,147,255,.22)",
                    borderRadius: "7px",
                    padding: "1px 6px",
                  }}
                >
                  {src}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// MetricBar
// ---------------------------------------------------------------------------

interface MetricBarProps {
  label: string
  value: number | undefined
  color: string
  trackColor: string
  labelColor: string
  /** Optional provenance. When absent, no tooltip renders and none is fabricated. */
  provenance?: Provenance
  reducedMotion: boolean
}

function MetricBar({
  label,
  value,
  color,
  trackColor,
  labelColor,
  provenance,
  reducedMotion,
}: MetricBarProps) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        {provenance !== undefined ? (
          <ProvenancePopover
            label={label}
            labelColor={labelColor}
            provenance={provenance}
            reducedMotion={reducedMotion}
          />
        ) : (
          <span
            className="font-mono text-[9px] font-bold uppercase tracking-[0.14em]"
            style={{ color: labelColor }}
          >
            {label}
          </span>
        )}
        <span
          className="font-mono text-[10px] font-bold"
          style={{ color: value !== undefined ? labelColor : "#666666" }}
        >
          {value !== undefined ? `${value}%` : "—"}
        </span>
      </div>
      <div
        className="h-1.5 overflow-hidden rounded-full"
        style={{ background: trackColor }}
        aria-hidden="true"
      >
        <div
          className="h-full rounded-full"
          style={{
            width: value !== undefined ? `${Math.min(100, Math.max(0, value))}%` : "0%",
            background: color,
            boxShadow: value !== undefined ? `0 0 8px ${color}` : "none",
            transition: reducedMotion ? "none" : "width 0.7s ease",
          }}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PlanningMetrics — public API
// ---------------------------------------------------------------------------

export interface PlanningMetricsProps {
  /** Facial nerve preservation rate 0–100. Omit when engine provides no data. */
  facialPres?: number
  /** Provenance for facial-pres bar. When absent no tooltip renders; nothing fabricated. */
  facialPresProvenance?: Provenance
  /** Hearing preservation rate 0–100. Omit when engine provides no data. */
  hearingPres?: number
  /** Provenance for hearing-pres bar. When absent no tooltip renders; nothing fabricated. */
  hearingPresProvenance?: Provenance
  /** Gross-total resection rate 0–100. Omit when engine provides no data. */
  gtr?: number
  /** Provenance for GTR bar. When absent no tooltip renders; nothing fabricated. */
  gtrProvenance?: Provenance
  /** Estimated OR time in hours. Omit when engine provides no data. */
  orTimeHr?: number
  /** CSF leak risk 0–100. Omit when engine provides no data. */
  csfLeakPct?: number
}

/**
 * planningHasData — true when the engine supplied at least one planning field.
 * Pure helper: used both to early-return null inside the panel and to gate the
 * Dossier hero column from Build.tsx, so the two stay in lockstep.
 */
export function planningHasData(p: PlanningMetricsProps): boolean {
  return (
    p.facialPres !== undefined ||
    p.hearingPres !== undefined ||
    p.gtr !== undefined ||
    p.orTimeHr !== undefined ||
    p.csfLeakPct !== undefined
  )
}

export default function PlanningMetrics(props: PlanningMetricsProps) {
  const {
    facialPres,
    facialPresProvenance,
    hearingPres,
    hearingPresProvenance,
    gtr,
    gtrProvenance,
    orTimeHr,
    csfLeakPct,
  } = props
  const reducedMotion = useReducedMotion()

  // Honest hide-when-empty: with no engine-provided planning fields there is
  // nothing to show, so render nothing rather than a dead "not available" box.
  // Reappears automatically once any field is populated.
  if (!planningHasData(props)) return null

  return (
    <div
      className="flex flex-col gap-4 p-4"
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
        Planning Metrics
      </p>

      <div className="flex flex-col gap-3">
        <MetricBar
          label="Facial pres."
          value={facialPres}
          color="#34e07f"
          trackColor="rgba(52,224,127,.12)"
          labelColor="#34e07f"
          provenance={facialPresProvenance}
          reducedMotion={reducedMotion}
        />
        <MetricBar
          label="Hearing pres."
          value={hearingPres}
          color="#ffc94d"
          trackColor="rgba(255,201,77,.12)"
          labelColor="#ffc94d"
          provenance={hearingPresProvenance}
          reducedMotion={reducedMotion}
        />
        <MetricBar
          label="GTR"
          value={gtr}
          color="#6b93ff"
          trackColor="rgba(107,147,255,.12)"
          labelColor="#6b93ff"
          provenance={gtrProvenance}
          reducedMotion={reducedMotion}
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div
          className="flex flex-col gap-0.5 p-3"
          style={{
            background: "rgba(255,255,255,.04)",
            border: "1px solid rgba(255,255,255,.07)",
            borderRadius: "11px",
          }}
        >
          <span
            className="font-mono text-[9px] uppercase tracking-[0.14em]"
            style={{ color: "#8a8a8a" }}
          >
            EST OR TIME
          </span>
          <span
            className="font-mono text-base font-bold"
            style={{ color: "#ededed" }}
          >
            {orTimeHr !== undefined ? `${orTimeHr} hr` : "—"}
          </span>
        </div>
        <div
          className="flex flex-col gap-0.5 p-3"
          style={{
            background: "rgba(255,90,90,.07)",
            border: "1px solid rgba(255,90,90,.18)",
            borderRadius: "11px",
          }}
        >
          <span
            className="font-mono text-[9px] uppercase tracking-[0.14em]"
            style={{ color: "#ff5a5a" }}
          >
            CSF LEAK RISK
          </span>
          <span
            className="font-mono text-base font-bold"
            style={{ color: "#ff5a5a" }}
          >
            {csfLeakPct !== undefined ? `${csfLeakPct}%` : "—"}
          </span>
        </div>
      </div>
    </div>
  )
}
