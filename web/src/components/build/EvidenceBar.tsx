import type { EvidenceSummary } from "@/lib/api"

/** Restyled palette-aware evidence bar.
    Three lanes: Supported (sage) · To-Verify (ochre) · Quarantined (brick).
    Glass panel header, flat stat tiles, mono labels. */
export default function EvidenceBar({ summary }: { summary: EvidenceSummary }) {
  const total = summary.supported + summary.to_verify + summary.quarantined
  const pct = (n: number) => (total ? Math.round((n / total) * 100) : 0)

  const lanes = [
    {
      n: summary.supported,
      color: "#5fa86f",
      glow: "rgba(95,168,111,.4)",
      label: "Supported",
    },
    {
      n: summary.to_verify,
      color: "#d89a3f",
      glow: "rgba(216,154,63,.4)",
      label: "To verify",
    },
    {
      n: summary.quarantined,
      color: "#c0564f",
      glow: "rgba(192,86,79,.4)",
      label: "Quarantined",
    },
  ]

  return (
    <div
      className="p-5"
      style={{
        background: "linear-gradient(160deg,rgba(255,255,255,.05),rgba(255,255,255,.012))",
        border: "1px solid rgba(255,255,255,.09)",
        backdropFilter: "blur(14px)",
        borderRadius: "16px",
      }}
    >
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h2
          className="font-mono text-[11px] font-bold uppercase tracking-[0.18em]"
          style={{ color: "#6fc0b8" }}
        >
          Evidence integrity
        </h2>
        <span className="tnum font-mono text-[11px]" style={{ color: "#766a64" }}>
          {total} claims
        </span>
      </div>

      {/* Segmented progress bar */}
      <div
        className="flex h-2 w-full overflow-hidden"
        style={{ borderRadius: "4px", background: "rgba(255,255,255,.06)" }}
        role="img"
        aria-label={`Evidence: ${summary.supported} supported, ${summary.to_verify} to verify, ${summary.quarantined} quarantined`}
      >
        {lanes.map((lane, i) =>
          lane.n > 0 ? (
            <div
              key={i}
              className="h-full transition-all"
              style={{
                width: `${pct(lane.n)}%`,
                background: lane.color,
                boxShadow: `0 0 6px ${lane.glow}`,
              }}
            />
          ) : null,
        )}
      </div>

      {/* Stat tiles */}
      <div className="mt-4 grid grid-cols-3 gap-3">
        {lanes.map((lane, i) => (
          <div
            key={i}
            className="px-3 py-2.5"
            style={{
              background: "rgba(255,255,255,.04)",
              border: "1px solid rgba(255,255,255,.07)",
              borderRadius: "10px",
            }}
          >
            <div
              className="tnum font-display text-xl font-bold leading-none"
              style={{ color: lane.color }}
            >
              {lane.n}
            </div>
            <div
              className="mt-1 font-mono text-[9px] font-bold uppercase tracking-[0.14em]"
              style={{ color: lane.color }}
            >
              {lane.label}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
