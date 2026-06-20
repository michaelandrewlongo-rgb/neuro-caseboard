/**
 * CitationAudit — Ask surface telemetry panel (Task 6a).
 *
 * HONEST DATA MAPPING (clinical tool — binding):
 * Drives EvidenceGauge from REAL counts derived from AskResponse:
 *   - grounded = citations.length            (corpus / textbook citations — indexed and grounded)
 *   - toLit    = literature?.citations.length ?? 0  (PubMed literature — not from the grounded corpus)
 *   - total    = grounded + toLit
 *
 * No counts are fabricated. If the response carries zero citations the gauge renders at zero.
 */

import { EvidenceGauge } from "@/components/charts/EvidenceGauge"
import type { Citation, Literature } from "@/lib/api"

interface CitationAuditProps {
  citations: Citation[]
  literature: Literature | null
}

export function CitationAudit({ citations, literature }: CitationAuditProps) {
  const grounded = citations.length
  const toLit = literature?.citations.length ?? 0
  const total = grounded + toLit

  // Outer ring — corpus citations (sage, grounded)
  // Inner ring — literature citations (ochre, to verify)
  const rings = [
    {
      r: 68,
      frac: total > 0 ? grounded / total : 0,
      color: "#5fa86f",
      glow: "#5fa86f",
    },
    {
      r: 50,
      frac: total > 0 ? toLit / total : 0,
      color: "#d89a3f",
      glow: "#d89a3f",
    },
  ]

  return (
    <div className="surface p-5 flex flex-col gap-4" aria-label="Citation audit">
      <p
        className="font-mono text-[11px] font-bold uppercase tracking-[0.18em]"
        style={{ color: "#ff7363" }}
      >
        Citation Audit
      </p>
      <div className="flex items-center gap-6">
        <div style={{ width: 160, height: 160, flexShrink: 0 }}>
          <EvidenceGauge rings={rings} size={160}>
            <div className="flex flex-col items-center">
              <span
                className="tnum font-mono text-[17px] font-bold leading-none"
                style={{ color: "#f1ece6" }}
              >
                {grounded}/{total}
              </span>
              <span
                className="mt-1 font-mono text-[8.5px] uppercase tracking-[0.18em]"
                style={{ color: "#978d86" }}
              >
                GROUNDED
              </span>
            </div>
          </EvidenceGauge>
        </div>
        <div className="flex flex-col gap-2.5">
          <div className="flex items-center gap-2">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ background: "#5fa86f", boxShadow: "0 0 6px #5fa86f" }}
            />
            <span className="font-mono text-[10px] uppercase tracking-[0.12em]" style={{ color: "#a79e98" }}>
              Corpus ({grounded})
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ background: "#d89a3f", boxShadow: "0 0 6px #d89a3f" }}
            />
            <span className="font-mono text-[10px] uppercase tracking-[0.12em]" style={{ color: "#a79e98" }}>
              Literature ({toLit})
            </span>
          </div>
          {total === 0 && (
            <p
              className="mt-1 font-mono text-[9px] uppercase tracking-[0.1em]"
              style={{ color: "#766a64" }}
            >
              No citations in response
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
