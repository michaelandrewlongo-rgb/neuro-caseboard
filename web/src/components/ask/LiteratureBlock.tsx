import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"
import { citify } from "@/lib/citations"
import type { Literature } from "@/lib/api"

// Muted plum — contemporary-literature lane accent (per design: only surface that uses plum).
const PLUM = "#a98bc4"
const PLUM_BRIGHT = "#c4b0d8"
const PLUM_BORDER = "rgba(150,120,170,.22)"
const PLUM_BG = "rgba(150,120,170,.08)"

const components: Components = {
  p: ({ children }) => (
    <p className="my-3" style={{ fontSize: "15px", lineHeight: "1.72", color: "#ece7e1" }}>
      {citify(children)}
    </p>
  ),
}

/** Contemporary-literature lane (PubMed). Plum accent throughout; [L#] markers resolve to
    the PMID/DOI list below. Separate citation axis from the corpus [n] sources. */
export default function LiteratureBlock({ literature }: { literature: Literature }) {
  if (!literature.narrative) return null
  return (
    <section
      className="rounded-[var(--radius-lg)] p-6"
      style={{
        background: PLUM_BG,
        borderWidth: "1px",
        borderStyle: "solid",
        borderColor: PLUM_BORDER,
        borderLeftWidth: "3px",
        borderLeftColor: PLUM,
      }}
    >
      <h2 className="eyebrow mb-3" style={{ color: PLUM }}>
        Contemporary Literature · PubMed
      </h2>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {literature.narrative}
      </ReactMarkdown>
      {literature.citations.length > 0 && (
        <ol
          className="mt-4 flex flex-col gap-2.5 pt-4"
          style={{ borderTop: `1px solid ${PLUM_BORDER}` }}
        >
          {literature.citations.map((c) => (
            <li key={c.n ?? c.pmid} id={`src-literature-${c.n}`} className="flex scroll-mt-20 gap-3 text-sm">
              <span
                className="shrink-0 font-mono text-xs font-bold"
                style={{ color: PLUM_BRIGHT }}
              >
                [L{c.n}]
              </span>
              <span className="leading-snug text-muted-foreground">
                <span style={{ color: "#ece7e1" }}>{c.title}</span> — {c.journal}
                {c.year ? ` ${c.year}` : ""}
                {" · "}
                <a
                  href={c.link}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="underline underline-offset-2"
                  style={{ color: PLUM, textDecorationColor: PLUM }}
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
