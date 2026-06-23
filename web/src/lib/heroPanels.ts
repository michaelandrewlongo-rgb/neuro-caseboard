/**
 * heroPanels — pure layout helper for the Dossier hero "telemetry grid".
 *
 * The hero shows up to three panels (Risk Topology, Evidence Integrity,
 * Planning Metrics) but only renders the ones backed by real engine data
 * (honest hide-when-empty). This maps the count of visible panels to the
 * grid's `gridTemplateColumns` so collapsed panels never leave dead columns.
 */
export function heroGridColumns(visible: number): string {
  if (visible >= 3) return "1.15fr 1fr 1.05fr"
  if (visible === 2) return "1fr 1fr"
  if (visible === 1) return "minmax(0, 460px)"
  return ""
}

/** The engine-populated numeric fields that decide whether Planning Metrics has data. */
export interface PlanningFields {
  facialPres?: number
  hearingPres?: number
  gtr?: number
  orTimeHr?: number
  csfLeakPct?: number
}

/**
 * planningHasData — true when the engine supplied at least one planning field.
 * Pure helper kept here (not in the component) so it carries no React import and
 * doesn't trip react-refresh/only-export-components. Used both to early-return
 * null inside <PlanningMetrics/> and to gate the Dossier hero column from
 * Build.tsx, so the two stay in lockstep.
 */
export function planningHasData(p: PlanningFields): boolean {
  return (
    p.facialPres !== undefined ||
    p.hearingPres !== undefined ||
    p.gtr !== undefined ||
    p.orTimeHr !== undefined ||
    p.csfLeakPct !== undefined
  )
}
