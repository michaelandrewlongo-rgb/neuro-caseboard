import type { BriefingReference } from "@/lib/api"

// T# (textbook) and L# (PubMed) namespaces stay distinct on the references surface (spec §8/§11).
// In its own module (not the component file) so Fast Refresh stays component-only.
export function splitRefs(refs: BriefingReference[]): {
  textbook: BriefingReference[]
  pubmed: BriefingReference[]
} {
  return {
    textbook: refs.filter((r) => r.kind === "textbook"),
    pubmed: refs.filter((r) => r.kind === "pubmed"),
  }
}
