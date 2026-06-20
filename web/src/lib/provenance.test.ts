import { describe, it, expect } from "vitest"
import {
  classifyMarker,
  splitCitations,
  PROVENANCE_LABEL,
  type Provenance,
} from "./provenance"

describe("citation provenance (BACKLOG P5 #14)", () => {
  it("classifies textbook / literature / card markers with jump anchors", () => {
    expect(classifyMarker("[5]")).toMatchObject({ kind: "textbook", n: 5, anchor: "src-textbook-5" })
    expect(classifyMarker("[L3]")).toMatchObject({ kind: "literature", n: 3, anchor: "src-literature-3" })
    expect(classifyMarker("[C2]")).toMatchObject({ kind: "card", n: 2, anchor: "src-card-2" })
  })

  it("returns null for non-markers", () => {
    expect(classifyMarker("hello")).toBeNull()
    expect(classifyMarker("[X9]")).toBeNull()
  })

  it("splits prose into ordered text and marker segments", () => {
    const segs = splitCitations("The PICA [1] supplies the medulla [L2] per my card [C3].")
    const kinds = segs.flatMap((s) => ("marker" in s ? [s.marker.kind] : []))
    expect(kinds).toEqual<Provenance[]>(["textbook", "literature", "card"])
    // text segments are preserved in order
    expect("text" in segs[0] && segs[0].text.startsWith("The PICA")).toBe(true)
  })

  it("labels every provenance kind for hover/legend", () => {
    expect(Object.keys(PROVENANCE_LABEL).sort()).toEqual(["card", "literature", "textbook"])
  })
})
