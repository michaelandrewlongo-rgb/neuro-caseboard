/**
 * RiskRadar — dependency-free polar SVG chart.
 *
 * Renders a radar polygon for anatomy-at-risk scores, with an optional
 * dashed post-mitigation overlay. Used by Dossier (Tasks 4) and Ask
 * (Task 6) surfaces.
 *
 * Prop signature (downstream tasks depend on this exactly):
 *   RiskRadar({ axes, size, withMit })
 *   axes  — array of { k: string; risk: number; mit?: number }
 *   size  — square SVG side length in px
 *   withMit — render the dashed teal mitigation polygon?
 */
import { useId } from "react"

type RadarAxis = { k: string; risk: number; mit?: number }

export function RiskRadar({
  axes,
  size,
  withMit = false,
}: {
  axes: RadarAxis[]
  size: number
  withMit?: boolean
}) {
  // Unique id suffix so the radialGradient def is collision-safe when
  // two RiskRadar instances appear on the same page.
  const uid = useId().replace(/:/g, "")
  const gradId = `ncRadar-${uid}`
  const filterId = `ncRadarShadow-${uid}`

  const cx = size / 2
  const cy = size / 2
  const R = size / 2 - 30
  const n = axes.length

  /** Polar angle for axis i — starts at 12 o'clock, clockwise */
  const ang = (i: number) => -Math.PI / 2 + (i * 2 * Math.PI) / n

  /** Cartesian point at axis i, fraction f of R */
  const pt = (i: number, f: number): [number, number] => [
    cx + Math.cos(ang(i)) * R * f,
    cy + Math.sin(ang(i)) * R * f,
  ]

  /** Closed SVG path connecting all axis points at fraction f */
  const ringPath = (f: number): string =>
    axes
      .map((_, i) => {
        const [x, y] = pt(i, f)
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`
      })
      .join(" ") + "Z"

  /** Data polygon for the given numeric key */
  const dataPath = (getter: (a: RadarAxis) => number): string =>
    axes
      .map((a, i) => {
        const [x, y] = pt(i, getter(a) / 100)
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`
      })
      .join(" ") + "Z"

  // ── 4 grid rings ────────────────────────────────────────────────
  const gridRings = ([0.25, 0.5, 0.75, 1] as const).map((f, i) => (
    <path
      key={`r${i}`}
      d={ringPath(f)}
      fill="none"
      stroke="rgba(255,255,255,0.07)"
      strokeWidth={1}
    />
  ))

  // ── Spokes from center to perimeter ─────────────────────────────
  const spokes = axes.map((_, i) => {
    const [x, y] = pt(i, 1)
    return (
      <line
        key={`s${i}`}
        x1={cx}
        y1={cy}
        x2={x}
        y2={y}
        stroke="rgba(255,255,255,0.06)"
        strokeWidth={1}
      />
    )
  })

  // ── Risk value dots ──────────────────────────────────────────────
  const dotsRisk = axes.map((a, i) => {
    const [x, y] = pt(i, a.risk / 100)
    return <circle key={`d${i}`} cx={x} cy={y} r={2.6} fill="#d8413a" />
  })

  // ── Mono axis labels at R * 1.16 ────────────────────────────────
  const axisLabels = axes.map((a, i) => {
    const [x, y] = pt(i, 1.16)
    return (
      <text
        key={`t${i}`}
        x={x}
        y={y}
        fill="#897d77"
        fontSize={8.5}
        fontFamily="'JetBrains Mono', monospace"
        letterSpacing="0.04em"
        textAnchor="middle"
        dominantBaseline="middle"
      >
        {a.k}
      </text>
    )
  })

  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      width="100%"
      height="100%"
      style={{ overflow: "visible" }}
      aria-hidden="true"
    >
      <defs>
        {/* Radial gradient fill for the risk polygon */}
        <radialGradient id={gradId} cx="50%" cy="50%" r="60%">
          <stop offset="0%" stopColor="rgba(216,65,58,0.42)" />
          <stop offset="100%" stopColor="rgba(190,45,50,0.1)" />
        </radialGradient>
        {/* Drop-shadow filter for the risk polygon */}
        <filter id={filterId} x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur in="SourceAlpha" stdDeviation="3" result="blur" />
          <feFlood floodColor="rgba(216,65,58,0.55)" result="color" />
          <feComposite in="color" in2="blur" operator="in" result="shadow" />
          <feMerge>
            <feMergeNode in="shadow" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Grid rings */}
      {gridRings}

      {/* Axis spokes */}
      {spokes}

      {/* Post-mitigation overlay (dashed teal) — rendered beneath risk polygon */}
      {withMit && (
        <path
          d={dataPath((a) => a.mit ?? 0)}
          fill="rgba(63,150,144,0.16)"
          stroke="#3f9690"
          strokeWidth={1.3}
          strokeDasharray="3 3"
        />
      )}

      {/* Risk polygon — crimson radial fill + glow */}
      <path
        d={dataPath((a) => a.risk)}
        fill={`url(#${gradId})`}
        stroke="#d8413a"
        strokeWidth={1.6}
        filter={`url(#${filterId})`}
      />

      {/* Risk value dots */}
      {dotsRisk}

      {/* Axis labels */}
      {axisLabels}
    </svg>
  )
}
