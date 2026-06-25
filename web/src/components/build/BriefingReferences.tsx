import type { BriefingReference } from "@/lib/api"
import { splitRefs } from "./briefingRefs"

function refExtra(meta: Record<string, unknown> | undefined): string {
  return (["pmid", "doi", "url", "page", "book"] as const)
    .map((k) => meta?.[k])
    .filter(Boolean)
    .map(String)
    .join(" · ")
}

function RefList({ title, refs }: { title: string; refs: BriefingReference[] }) {
  if (!refs.length) return null
  return (
    <div>
      <h3 className="font-display text-sm font-bold text-foreground">{title}</h3>
      <ul className="mt-2 flex flex-col gap-2">
        {refs.map((r) => {
          const extra = refExtra(r.meta)
          return (
            <li key={r.ref_id} className="text-sm text-foreground">
              <span className="font-mono text-xs font-bold text-secondary">{r.ref_id}</span> {r.citation}
              {extra && <span className="text-muted-foreground"> · {extra}</span>}
              {r.sections && r.sections.length > 0 && (
                <span className="mt-0.5 block font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                  supports: {r.sections.join(", ")}
                </span>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default function BriefingReferences({ references }: { references: BriefingReference[] }) {
  if (!references.length) return null
  const { textbook, pubmed } = splitRefs(references)
  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-5">
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-secondary">
        References &amp; Evidence
      </p>
      <RefList title="Textbook sources" refs={textbook} />
      <RefList title="Contemporary literature" refs={pubmed} />
    </section>
  )
}
