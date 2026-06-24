import PipelineLoader from "@/components/PipelineLoader"

/** Real Ask pipeline stages — the synthesis provider name stays out of the UI. */
const ASK_STEPS = [
  "Searching your textbook corpus…",
  "Ranking the most relevant passages…",
  "Synthesizing a cited answer…",
  "Scanning recent PubMed literature…",
]

/** Slow-call loader for the Ask surface — a thin wrapper over the shared, monotonic
    PipelineLoader checklist (consolidates the two near-identical loaders). */
export default function AskLoader() {
  return (
    <PipelineLoader
      steps={ASK_STEPS}
      estimate="Usually about 2 minutes — retrieval, citation-grounded synthesis, and a live PubMed lookup."
      eyebrow="Ask · Corpus Retrieval"
      srText="Working on your answer — searching the corpus, synthesizing a cited answer, and scanning recent literature. This usually takes about 2 minutes."
      stepIntervalMs={20000}
    />
  )
}
