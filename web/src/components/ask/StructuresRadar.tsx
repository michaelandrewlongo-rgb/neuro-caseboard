/**
 * StructuresRadar — Ask surface telemetry panel (Task 6a).
 *
 * HONEST DATA MAPPING (clinical tool — binding):
 * Intended to wrap RiskRadar with axes = anatomy named in the answer.
 *
 * The AskResponse carries a free-text `answer` string only; no structured
 * anatomy list or per-structure risk scores are present in the API response.
 * Extracting anatomy axes from raw text would risk fabrication — this panel
 * therefore renders an honest "not available" state.
 *
 * When a future engine version exposes a structured anatomy index, replace the
 * placeholder below with a real <RiskRadar axes={...} size={160} /> call.
 */

// Reserved for future use once the engine exposes structured anatomy data:
// import { RiskRadar } from "@/components/charts/RiskRadar"

/** Props reserved for future anatomy extraction from the answer text. */
interface StructuresRadarProps {
  /** The raw answer text. Reserved for future structured anatomy extraction — currently unused. */
  answer: string
}

// --- Static placeholder polar grid geometry (mirrors RiskRadar's 6-spoke hexagonal layout) ---
const SIZE = 160
const CX = SIZE / 2
const CY = SIZE / 2
const R = SIZE / 2 - 30
const PLACEHOLDER_SPOKES = 6
const GRID_FRACS = [0.25, 0.5, 0.75, 1] as const

function spokeAngle(i: number): number {
  return -Math.PI / 2 + (i * 2 * Math.PI) / PLACEHOLDER_SPOKES
}

function spokeEnd(i: number): [number, number] {
  const a = spokeAngle(i)
  return [CX + Math.cos(a) * R, CY + Math.sin(a) * R]
}

function gridRingPath(frac: number): string {
  return (
    Array.from({ length: PLACEHOLDER_SPOKES }, (_, i) => {
      const a = spokeAngle(i)
      const x = (CX + Math.cos(a) * R * frac).toFixed(1)
      const y = (CY + Math.sin(a) * R * frac).toFixed(1)
      return `${i === 0 ? "M" : "L"}${x} ${y}`
    }).join(" ") + "Z"
  )
}

export function StructuresRadar({ answer }: StructuresRadarProps) {
  // Use answer presence to set accessible label; no anatomy data is extracted (avoids fabrication).
  const ariaLabel =
    answer.length > 0
      ? "Structures referenced — anatomy index not available in this response"
      : "Structures referenced"

  return (
    <div
      className="surface p-5 flex flex-col gap-3"
      aria-label={ariaLabel}
    >
      <p
        className="font-mono text-[11px] font-bold uppercase tracking-[0.18em]"
        style={{ color: "#ff7363" }}
      >
        Structures Referenced
      </p>
      <div className="flex flex-col items-center justify-center gap-3 flex-1">
        {/* Faded placeholder polar grid — conveys chart type without fabricating data */}
        <div style={{ width: SIZE, height: SIZE, opacity: 0.18 }} aria-hidden="true">
          <svg viewBox={`0 0 ${SIZE} ${SIZE}`} width="100%" height="100%">
            {GRID_FRACS.map((f, i) => (
              <path
                key={i}
                d={gridRingPath(f)}
                fill="none"
                stroke="rgba(255,255,255,0.7)"
                strokeWidth={1}
              />
            ))}
            {Array.from({ length: PLACEHOLDER_SPOKES }, (_, i) => {
              const [x, y] = spokeEnd(i)
              return (
                <line
                  key={i}
                  x1={CX}
                  y1={CY}
                  x2={x}
                  y2={y}
                  stroke="rgba(255,255,255,0.55)"
                  strokeWidth={1}
                />
              )
            })}
          </svg>
        </div>
        <p
          className="font-mono text-[9.5px] uppercase tracking-[0.12em] text-center leading-[1.7]"
          style={{ color: "#766a64" }}
        >
          Anatomy index
          <br />
          not available in this response
        </p>
      </div>
    </div>
  )
}
