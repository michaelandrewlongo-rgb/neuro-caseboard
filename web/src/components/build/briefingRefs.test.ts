import { describe, it, expect } from "vitest"
import { splitRefs } from "./BriefingReferences"
import type { BriefingReference } from "@/lib/api"

const refs: BriefingReference[] = [
  { ref_id: "T1", kind: "textbook", citation: "Youmans ch.12", meta: {}, sections: ["pathology"] },
  { ref_id: "L1", kind: "pubmed", citation: "Smith 2024", meta: { pmid: "123" }, sections: ["management"] },
  { ref_id: "T2", kind: "textbook", citation: "Rhoton 2002", meta: {}, sections: ["technique"] },
]

describe("splitRefs", () => {
  it("keeps T# and L# namespaces distinct", () => {
    const { textbook, pubmed } = splitRefs(refs)
    expect(textbook.map((r) => r.ref_id)).toEqual(["T1", "T2"])
    expect(pubmed.map((r) => r.ref_id)).toEqual(["L1"])
  })
})
