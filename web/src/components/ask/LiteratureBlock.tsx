import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import type { Literature } from "@/lib/api"

/** Contemporary-literature lane (PubMed). A SEPARATE axis from the corpus [n] sources: its
    narrative carries [L#] markers that resolve to the PMID/DOI list below. */
export default function LiteratureBlock({ literature }: { literature: Literature }) {
  if (!literature.narrative) return null
  return (
    <section className="rounded-xl border border-teal/25 bg-teal/[0.04] p-6">
      <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-teal">
        Contemporary Literature · PubMed
      </h2>
      <div className="leading-relaxed text-ink">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{literature.narrative}</ReactMarkdown>
      </div>
      {literature.citations.length > 0 && (
        <ol className="mt-4 flex flex-col gap-2 border-t border-navy-700/50 pt-4">
          {literature.citations.map((c) => (
            <li key={c.n ?? c.pmid} className="flex gap-3 text-sm">
              <span className="shrink-0 font-mono text-xs text-teal">[L{c.n}]</span>
              <span className="text-ink-dim">
                <span className="text-ink">{c.title}</span>{" "}
                — {c.journal}
                {c.year ? ` ${c.year}` : ""}
                {" · "}
                <a
                  href={c.link}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-teal underline decoration-teal/40 underline-offset-2 hover:decoration-teal"
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
