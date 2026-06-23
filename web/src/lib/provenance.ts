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
// Matches a whole bracket of ONE OR MORE comma-separated tokens: [2] · [2, 11] · [L2, C3].
const SPLIT_RE = /(\[\s*(?:L|C)?\d+(?:\s*,\s*(?:L|C)?\d+)*\s*\])/g
// Anchored variant (no /g) for testing whether a split part IS a bracket group.
const GROUP_RE = /^\[\s*(?:L|C)?\d+(?:\s*,\s*(?:L|C)?\d+)*\s*\]$/

export function classifyMarker(token: string): Marker | null {
  const m = MARKER_RE.exec(token)
  if (!m) return null
  const kind: Provenance = m[1] === "L" ? "literature" : m[1] === "C" ? "card" : "textbook"
  const n = Number(m[2])
  return { raw: token, kind, n, label: m[2], anchor: `src-${kind}-${n}` }
}

export type Segment = { text: string } | { marker: Marker }

/**
 * Split prose into ordered text / marker segments (markers classified by provenance).
 *
 * A bracket group may hold one OR MORE comma-separated tokens; each becomes its own marker
 * segment, so a combined `[2, 11]` yields two chips just like two single `[2]` `[11]` would.
 * Single `[n]` is the 1-token case → identical output to the original parser.
 */
export function splitCitations(text: string): Segment[] {
  const segments: Segment[] = []
  for (const part of text.split(SPLIT_RE)) {
    if (part === "") continue
    if (GROUP_RE.test(part)) {
      // Extract each individual token (`L3`, `C2`, `11`) and classify it on its own.
      for (const tok of part.match(/(?:L|C)?\d+/g) ?? []) {
        const marker = classifyMarker(`[${tok}]`)
        if (marker) segments.push({ marker })
      }
    } else {
      segments.push({ text: part })
    }
  }
  return segments
}
