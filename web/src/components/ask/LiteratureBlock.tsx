import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"
import { citify } from "@/lib/citations"
import type { Literature } from "@/lib/api"

const components: Components = {
  p: ({ children }) => <p className="reading my-3">{citify(children)}</p>,
}

/** Contemporary-literature lane (PubMed). A SEPARATE axis from the corpus [n] sources: its
    narrative carries [L#] markers that resolve to the PMID/DOI list below. */
export default function LiteratureBlock({ literature }: { literature: Literature }) {
  if (!literature.narrative) return null
  return (
    <section className="border-2 border-border border-l-[6px] border-l-accent bg-card p-6 shadow-card">
      <h2 className="eyebrow mb-3 !text-accent">Contemporary Literature · PubMed</h2>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {literature.narrative}
      </ReactMarkdown>
      {literature.citations.length > 0 && (
        <ol className="mt-4 flex flex-col gap-2.5 border-t-2 border-border pt-4">
          {literature.citations.map((c) => (
            <li key={c.n ?? c.pmid} className="flex gap-3 text-sm">
              <span className="shrink-0 font-mono text-xs font-bold text-accent">[L{c.n}]</span>
              <span className="leading-snug text-muted-foreground">
                <span className="text-foreground">{c.title}</span> — {c.journal}
                {c.year ? ` ${c.year}` : ""}
                {" · "}
                <a
                  href={c.link}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-accent underline decoration-accent underline-offset-2"
                >
                  {c.doi ? `doi:${c.doi}` : `PMID ${c.pmid}`}
                </a>
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
