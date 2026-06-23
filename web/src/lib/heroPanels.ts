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
