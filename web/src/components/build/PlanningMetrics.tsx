/**
 * PlanningMetrics — Dossier telemetry panel (Task 4b).
 *
 * Displays labeled outcome bars (Facial-pres / Hearing-pres / GTR) and
 * stat tiles (EST OR TIME / CSF LEAK RISK).
 *
 * HONEST DATA MAPPING (clinical tool — binding):
 * BuildResponse carries NO backing fields for these clinical percentages or
 * timing estimates. Props are typed for future engine support, but until the
 * engine exposes planning fields all values are absent and the panel renders
 * an honest "no planning data from engine" state.
 * Do NOT pass fabricated numbers.
 */

interface MetricBarProps {
  label: string
  value: number | undefined
  color: string
  trackColor: string
  labelColor: string
}

function MetricBar({ label, value, color, trackColor, labelColor }: MetricBarProps) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span
          className="font-mono text-[9px] font-bold uppercase tracking-[0.14em]"
          style={{ color: labelColor }}
        >
          {label}
        </span>
        <span
          className="font-mono text-[10px] font-bold"
          style={{ color: value !== undefined ? labelColor : "#766a64" }}
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
            transition: "width 0.7s ease",
          }}
        />
      </div>
    </div>
  )
}

export interface PlanningMetricsProps {
  /** Facial nerve preservation rate 0–100. Omit when engine provides no data. */
  facialPres?: number
  /** Hearing preservation rate 0–100. Omit when engine provides no data. */
  hearingPres?: number
  /** Gross-total resection rate 0–100. Omit when engine provides no data. */
  gtr?: number
  /** Estimated OR time in hours. Omit when engine provides no data. */
  orTimeHr?: number
  /** CSF leak risk 0–100. Omit when engine provides no data. */
  csfLeakPct?: number
}

export default function PlanningMetrics({
  facialPres,
  hearingPres,
  gtr,
  orTimeHr,
  csfLeakPct,
}: PlanningMetricsProps) {
  const hasAnyData =
    facialPres !== undefined ||
    hearingPres !== undefined ||
    gtr !== undefined ||
    orTimeHr !== undefined ||
    csfLeakPct !== undefined

  return (
    <div
      className="flex flex-col gap-4 p-4"
      style={{
        background: "linear-gradient(160deg, rgba(255,255,255,.05), rgba(255,255,255,.012))",
        border: "1px solid rgba(255,255,255,.09)",
        borderRadius: "16px",
      }}
    >
      <p
        className="font-mono text-[9px] font-bold uppercase tracking-[0.18em]"
        style={{ color: "#6fc0b8" }}
      >
        Planning Metrics
      </p>

      {!hasAnyData ? (
        /* Honest "not available" state — no fabricated clinical numbers */
        <div className="flex flex-1 flex-col items-center justify-center gap-2 py-6 text-center">
          <span
            className="font-mono text-[9px] font-bold uppercase tracking-[0.14em]"
            style={{ color: "#766a64" }}
          >
            Not available
          </span>
          <p
            className="max-w-[16ch] text-[11px] leading-relaxed"
            style={{ color: "#897d77" }}
          >
            No planning data from engine
          </p>
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-3">
            <MetricBar
              label="Facial pres."
              value={facialPres}
              color="#5fa86f"
              trackColor="rgba(95,168,111,.12)"
              labelColor="#74c084"
            />
            <MetricBar
              label="Hearing pres."
              value={hearingPres}
              color="#d89a3f"
              trackColor="rgba(216,154,63,.12)"
              labelColor="#e0a86a"
            />
            <MetricBar
              label="GTR"
              value={gtr}
              color="#3f9690"
              trackColor="rgba(63,150,144,.12)"
              labelColor="#6fc0b8"
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
                style={{ color: "#897d77" }}
              >
                EST OR TIME
              </span>
              <span
                className="font-mono text-base font-bold"
                style={{ color: "#f1ece6" }}
              >
                {orTimeHr !== undefined ? `${orTimeHr} hr` : "—"}
              </span>
            </div>
            <div
              className="flex flex-col gap-0.5 p-3"
              style={{
                background: "rgba(192,86,79,.07)",
                border: "1px solid rgba(192,86,79,.18)",
                borderRadius: "11px",
              }}
            >
              <span
                className="font-mono text-[9px] uppercase tracking-[0.14em]"
                style={{ color: "#c0564f" }}
              >
                CSF LEAK RISK
              </span>
              <span
                className="font-mono text-base font-bold"
                style={{ color: "#ff7363" }}
              >
                {csfLeakPct !== undefined ? `${csfLeakPct}%` : "—"}
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
