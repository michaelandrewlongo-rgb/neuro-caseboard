import type { Citation } from "@/lib/api"

export default function SourcesList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null
  return (
    <section>
      <h2 className="eyebrow mb-3">Sources · textbook corpus</h2>
      <ol className="grid gap-2 sm:grid-cols-2">
        {citations.map((c) => (
          <li
            key={c.n ?? c.location}
            className="flex gap-3 border-2 border-border bg-muted px-3.5 py-2.5"
          >
            <span className="font-mono text-xs font-medium text-primary-ink">[{c.n}]</span>
            <span className="text-sm leading-snug text-muted-foreground">{c.location}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}
