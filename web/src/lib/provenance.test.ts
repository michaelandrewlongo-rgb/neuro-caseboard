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

describe("splitCitations — combined markers (P2 #6)", () => {
  it("expands a combined [2, 11] into two textbook markers, then a single [L3]", () => {
    const segs = splitCitations("see [2, 11] and [L3]")
    expect(segs).toHaveLength(5)
    expect(segs[0]).toEqual({ text: "see " })
    expect(segs[1]).toMatchObject({ marker: { n: 2, kind: "textbook" } })
    expect(segs[2]).toMatchObject({ marker: { n: 11, kind: "textbook" } })
    expect(segs[3]).toEqual({ text: " and " })
    expect(segs[4]).toMatchObject({ marker: { n: 3, kind: "literature" } })
  })

  it("handles a no-space combined marker a[2,11]b", () => {
    const segs = splitCitations("a[2,11]b")
    expect(segs).toHaveLength(4)
    expect(segs[0]).toEqual({ text: "a" })
    expect(segs[1]).toMatchObject({ marker: { n: 2, kind: "textbook" } })
    expect(segs[2]).toMatchObject({ marker: { n: 11, kind: "textbook" } })
    expect(segs[3]).toEqual({ text: "b" })
  })

  it("keeps mixed provenance within one bracket [L2, C3]", () => {
    const segs = splitCitations("[L2, C3]")
    expect(segs).toHaveLength(2)
    expect(segs[0]).toMatchObject({ marker: { n: 2, kind: "literature" } })
    expect(segs[1]).toMatchObject({ marker: { n: 3, kind: "card" } })
  })

  it("is non-regressive for a single marker x [5] y", () => {
    const segs = splitCitations("x [5] y")
    expect(segs).toHaveLength(3)
    expect(segs[0]).toEqual({ text: "x " })
    expect(segs[1]).toMatchObject({ marker: { n: 5, kind: "textbook" } })
    expect(segs[2]).toEqual({ text: " y" })
  })

  it("returns a single text segment when there are no markers", () => {
    expect(splitCitations("no citations here")).toEqual([{ text: "no citations here" }])
  })
})
