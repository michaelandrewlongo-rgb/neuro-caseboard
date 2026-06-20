/**
 * EvidenceGauge — dependency-free concentric-ring SVG chart.
 *
 * Each ring renders a background track circle and a progress arc
 * driven by stroke-dasharray. The center label is an HTML overlay
 * (absolutely positioned over the SVG) supplied via `children`.
 *
 * Prop signature (downstream tasks depend on this exactly):
 *   EvidenceGauge({ rings, size, children? })
 *   rings    — array of { r: number; frac: number; color: string; glow: string }
 *   size     — square side length in px (SVG + wrapper)
 *   children — optional center label rendered as an absolute overlay
 */
import type { ReactNode } from "react"

type GaugeRing = {
  r: number
  frac: number
  color: string
  glow: string
}

export function EvidenceGauge({
  rings,
  size,
  children,
}: {
  rings: GaugeRing[]
  size: number
  children?: ReactNode
}) {
  const cx = size / 2
  const cy = size / 2

  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg
        viewBox={`0 0 ${size} ${size}`}
        width="100%"
        height="100%"
        aria-hidden="true"
      >
        {rings.map((g, i) => {
          // Full circumference for this ring's radius
          const C = 2 * Math.PI * g.r
          const dashArray = `${(C * g.frac).toFixed(1)} ${C.toFixed(1)}`

          return (
            <g key={i}>
              {/* Background track — dark translucent ring */}
              <circle
                cx={cx}
                cy={cy}
                r={g.r}
                fill="none"
                stroke="rgba(255,255,255,0.06)"
                strokeWidth={9}
              />
              {/* Value arc — starts at 12 o'clock via rotate(-90) */}
              <circle
                cx={cx}
                cy={cy}
                r={g.r}
                fill="none"
                stroke={g.color}
                strokeWidth={9}
                strokeLinecap="round"
                strokeDasharray={dashArray}
                transform={`rotate(-90 ${cx} ${cy})`}
                style={{ filter: `drop-shadow(0 0 5px ${g.glow})` }}
              />
            </g>
          )
        })}
      </svg>

      {/* Center label: absolutely positioned HTML overlay, not baked into SVG */}
      {children != null && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            pointerEvents: "none",
          }}
        >
          {children}
        </div>
      )}
    </div>
  )
}
