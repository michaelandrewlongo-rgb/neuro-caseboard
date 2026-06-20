/**
 * Citation provenance (BACKLOG P5 #14).
 *
 * Pure parsing of inline citation markers into a typed provenance + jump anchor, so the renderer can
 * make every marker clickable (jump-to-source), hoverable (a provenance label), and visually
 * distinct by origin: textbook `[n]`, PubMed literature `[L#]`, and personal card `[C#]`.
 */
export type Provenance = "textbook" | "literature" | "card"

export interface Marker {
  raw: string // e.g. "[L3]"
  kind: Provenance
  n: number // 3
  label: string // "3" — shown inside the pill
  anchor: string // "src-literature-3" — id of the matching source-list entry to jump to
}

export const PROVENANCE_LABEL: Record<Provenance, string> = {
  textbook: "Textbook source",
  literature: "PubMed literature",
  card: "Personal card",
}

const MARKER_RE = /^\[(L|C)?(\d+)\]$/
const SPLIT_RE = /(\[(?:L|C)?\d+\])/g

export function classifyMarker(token: string): Marker | null {
  const m = MARKER_RE.exec(token)
  if (!m) return null
  const kind: Provenance = m[1] === "L" ? "literature" : m[1] === "C" ? "card" : "textbook"
  const n = Number(m[2])
  return { raw: token, kind, n, label: m[2], anchor: `src-${kind}-${n}` }
}

export type Segment = { text: string } | { marker: Marker }

/** Split prose into ordered text / marker segments (markers classified by provenance). */
export function splitCitations(text: string): Segment[] {
  return text
    .split(SPLIT_RE)
    .filter((s) => s !== "")
    .map((part): Segment => {
      const marker = classifyMarker(part)
      return marker ? { marker } : { text: part }
    })
}
