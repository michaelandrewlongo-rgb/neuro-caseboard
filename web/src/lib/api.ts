// Typed client for the FastAPI engine wrapper. All calls go through the Vite proxy at /api,
// so the browser sees one origin and there is no CORS / auth surface.

export interface HealthProbe {
  available?: boolean
  ok?: boolean
  enabled?: boolean
  provider?: string | null
  project?: string | null
  adc?: boolean
  client_import?: boolean
  index_dir?: string
  corpus_dir?: string
  table?: string
  source_db?: string
  ncbi_key?: boolean
  error?: string | null
  detail?: string | null
}

export interface Health {
  engine: boolean
  synth: boolean
  corpus: boolean
  cards_index: boolean
  ncbi_key: boolean
  detail: {
    engine: HealthProbe
    synth: HealthProbe
    corpus: HealthProbe
    cards: HealthProbe
    literature: HealthProbe
  }
}

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const res = await fetch("/api/health", { signal })
  if (!res.ok) {
    throw new Error(`/api/health returned ${res.status}`)
  }
  return (await res.json()) as Health
}

// ----- Ask -----------------------------------------------------------------------------------

export interface Citation {
  n: number | null
  book: string
  chapter: string
  page: number | null
  location: string
}

export interface Figure {
  source_n: number | null
  book: string
  chapter: string
  page: number | null
  caption: string
  location: string
  image_url: string | null
  image_available: boolean
}

export interface LitCitation {
  n: number | null
  pmid: string
  title: string
  journal: string
  year: number | null
  doi: string
  url: string
  link: string
}

export interface Literature {
  narrative: string
  citations: LitCitation[]
}

export interface Variant {
  label: string
  rewrite: string
}

export type AskResponse =
  | { kind: "answer"; answer: string; citations: Citation[]; figures: Figure[]; literature: Literature | null }
  | { kind: "clarification"; question: string; variants: Variant[] }
  | { kind: "unavailable"; reason: string }
  | { kind: "error"; error: string }

export async function askQuestion(question: string, signal?: AbortSignal,
                                  skipDisambiguation = false): Promise<AskResponse> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, skip_disambiguation: skipDisambiguation }),
    signal,
  })
  // Every outcome (answer / clarification / unavailable / error) is a JSON body carrying `kind`,
  // even on 4xx/5xx — so we forward the engine's honest state rather than throwing.
  const data = (await res.json().catch(() => null)) as AskResponse | null
  if (data && typeof data === "object" && "kind" in data) return data
  return { kind: "error", error: `Unexpected response (${res.status})` }
}

// ----- Build / dossier -----------------------------------------------------------------------

export interface DossierClaim {
  text: string
  why: string
  status: "supported" | "verify" | "quarantine"
  sub_items: string[]
  figure_ids: string[]
}

export interface DossierFigure {
  fig_id: string
  caption: string
  citation: string
  relevance: string
  claim_ref: string
  image_url: string | null
  image_available: boolean
}

export interface DossierSection {
  heading: string
  intro: string
  claims: DossierClaim[]
  figures: DossierFigure[]
  cross_refs: string[]
}

export interface AppendixEntry {
  heading: string
  items: string[]
  sources: string[]
}

export interface EvidenceSummary {
  supported: number
  to_verify: number
  quarantined: number
}

export interface Dossier {
  title: string
  summary: EvidenceSummary
  sections: DossierSection[]
  appendix: { entries: AppendixEntry[] }
}

export type BuildResponse =
  | { kind: "dossier"; build_id: string; topic: string; dossier: Dossier }
  | { kind: "unavailable"; reason: string }
  | { kind: "error"; error: string }

export async function buildDossier(
  topic: string,
  opts: { enrich: boolean; use_llm: boolean; use_prefs?: boolean },
  signal?: AbortSignal,
): Promise<BuildResponse> {
  const res = await fetch("/api/build", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, enrich: opts.enrich, use_llm: opts.use_llm, use_prefs: opts.use_prefs ?? true }),
    signal,
  })
  const data = (await res.json().catch(() => null)) as BuildResponse | null
  if (data && typeof data === "object" && "kind" in data) return data
  return { kind: "error", error: `Unexpected response (${res.status})` }
}

/** Fetch the dossier PDF (reuses the cached build_id — no rebuild). Returns a Blob to download. */
export async function fetchBuildPdf(build_id: string, signal?: AbortSignal): Promise<Blob> {
  const res = await fetch("/api/build/pdf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ build_id }),
    signal,
  })
  if (!res.ok) {
    const msg = await res
      .json()
      .then((d) => d?.error)
      .catch(() => null)
    throw new Error(msg || `PDF export failed (${res.status})`)
  }
  return await res.blob()
}

// ----- Cards ---------------------------------------------------------------------------------

export interface CardImage {
  image_url: string | null
  image_available: boolean
}

export interface Card {
  id: string
  deck: string
  tags: string
  flagged: string[]
  question_text: string
  answer_text: string
  images: CardImage[]
}

export type CardsResponse =
  | { kind: "cards"; query: string; cards: Card[] }
  | { kind: "not_built"; reason: string }
  | { kind: "unavailable"; reason: string }
  | { kind: "error"; error: string }

export async function searchCards(
  question: string,
  k: number,
  signal?: AbortSignal,
): Promise<CardsResponse> {
  const res = await fetch("/api/cards", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, k }),
    signal,
  })
  const data = (await res.json().catch(() => null)) as CardsResponse | null
  if (data && typeof data === "object" && "kind" in data) return data
  return { kind: "error", error: `Unexpected response (${res.status})` }
}

// ----- Rehearsal: feedback + remembered preferences -----------------------------------------

export type FeedbackMark = "wrong" | "missing" | "important"
export interface FeedbackItemIn {
  mark: FeedbackMark
  text: string
  section?: string
  note?: string
}

export type FeedbackResponse =
  | { kind: "dossier"; build_id: string; topic: string; profile: string; remembered: number; dossier: Dossier }
  | { kind: "unavailable"; reason: string }
  | { kind: "error"; error: string }

export async function submitFeedback(
  topic: string,
  items: FeedbackItemIn[],
  opts: { enrich: boolean; use_llm: boolean },
  signal?: AbortSignal,
): Promise<FeedbackResponse> {
  const res = await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, items, enrich: opts.enrich, use_llm: opts.use_llm }),
    signal,
  })
  const data = (await res.json().catch(() => null)) as FeedbackResponse | null
  if (data && typeof data === "object" && "kind" in data) return data
  return { kind: "error", error: `Unexpected response (${res.status})` }
}

export interface PreferenceOut {
  profile: string
  action: string
  pattern: string
  text: string
  why: string
  weight: number
  sources: string[]
}

export async function getPreferences(
  signal?: AbortSignal,
): Promise<{ count: number; preferences: PreferenceOut[] }> {
  const res = await fetch("/api/preferences", { signal })
  if (!res.ok) throw new Error(`/api/preferences returned ${res.status}`)
  return (await res.json()) as { count: number; preferences: PreferenceOut[] }
}
