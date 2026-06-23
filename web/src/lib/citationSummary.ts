/** Lane-honest Ask status line: names both citation sources (textbook corpus vs PubMed literature)
    without implying either is ungrounded. Counts come from real AskResponse fields. */
export function citationSummary(corpus: number, literature: number): string {
  const total = corpus + literature
  if (total === 0) return "No citations in this response"
  const noun = total === 1 ? "citation" : "citations"
  if (literature === 0) return `${total} ${noun} from your textbook corpus`
  return `${total} ${noun} · ${corpus} textbook corpus · ${literature} PubMed literature`
}
