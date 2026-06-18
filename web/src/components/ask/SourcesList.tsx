import type { Citation } from "@/lib/api"

export default function SourcesList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null
  return (
    <section>
      <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-ink-faint">Sources</h2>
      <ol className="flex flex-col gap-2">
        {citations.map((c) => (
          <li
            key={c.n ?? c.location}
            className="flex gap-3 rounded-md bg-navy-850/60 px-3 py-2 text-sm"
          >
            <span className="font-mono text-xs text-teal">[{c.n}]</span>
            <span className="text-ink-dim">{c.location}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}
