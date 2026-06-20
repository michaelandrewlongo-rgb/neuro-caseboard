import type { Citation } from "@/lib/api"

export default function SourcesList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null
  return (
    <section>
      <h2 className="eyebrow mb-3">Sources · textbook corpus</h2>
      <ol className="flex flex-col gap-2">
        {citations.map((c) => {
          // Prefer structured book/chapter/page; fall back to location string.
          const primary = c.book || c.location
          const parts: string[] = []
          if (c.chapter) parts.push(`Ch. ${c.chapter}`)
          if (c.page != null) parts.push(`p. ${c.page}`)
          const detail = parts.join(", ")
          return (
            <li
              key={c.n ?? c.location}
              id={`src-textbook-${c.n}`}
              className="flex scroll-mt-20 gap-3 rounded-[var(--radius-md)] px-3.5 py-2.5"
              style={{
                background: "rgba(63,150,144,.07)",
                border: "1px solid rgba(63,150,144,.18)",
              }}
            >
              <span
                className="shrink-0 font-mono text-xs font-semibold"
                style={{ color: "#6fc0b8" }}
              >
                [{c.n}]
              </span>
              <span className="text-sm leading-snug" style={{ color: "#a79e98" }}>
                <span className="font-medium" style={{ color: "#ece7e1" }}>
                  {primary}
                </span>
                {detail && <span className="ml-1">{detail}</span>}
              </span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
