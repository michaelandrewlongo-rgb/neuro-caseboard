import type { EvidenceSummary } from "@/lib/api"
import { Card, Stat } from "@/components/ui"

/** Single evidence axis (the engine's design: supported + to_verify + quarantined == total).
    No second "confidence" axis — mirrors the dossier model exactly. */
export default function EvidenceBar({ summary }: { summary: EvidenceSummary }) {
  const total = summary.supported + summary.to_verify + summary.quarantined
  const pct = (n: number) => (total ? (n / total) * 100 : 0)
  const segs = [
    { n: summary.supported, color: "bg-success" },
    { n: summary.to_verify, color: "bg-amber" },
    { n: summary.quarantined, color: "bg-primary" },
  ]

  return (
    <Card className="p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="eyebrow">Evidence summary</h2>
        <span className="tnum font-mono text-xs text-muted-foreground">{total} cards</span>
      </div>
      <div className="flex h-3 w-full overflow-hidden border-2 border-border bg-muted">
        {segs.map(
          (s, i) =>
            s.n > 0 && (
              <div
                key={i}
                className={`${s.color} ${i > 0 ? "border-l-2 border-border" : ""}`}
                style={{ width: `${pct(s.n)}%` }}
              />
            ),
        )}
      </div>
      <div className="mt-4 grid grid-cols-3 gap-3">
        <Stat value={summary.supported} label="corpus-supported" tone="success" />
        <Stat value={summary.to_verify} label="needs verification" tone="amber" />
        <Stat value={summary.quarantined} label="quarantined" tone="signal" />
      </div>
    </Card>
  )
}
