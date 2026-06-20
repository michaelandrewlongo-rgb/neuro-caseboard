import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"
import { citify } from "@/lib/citations"

// Body: 15px / 1.72 line-height / #ededed (warm body tone from the Grounded Anatomical palette).
const BODY: React.CSSProperties = { fontSize: "15px", lineHeight: "1.72", color: "#ededed" }

// Blockquote → ochre VERIFY callout (engine uses "> text" markdown for flagged claims).
const components: Components = {
  h2: ({ children }) => (
    <h2 className="mt-7 mb-3 font-display text-xl font-bold" style={{ color: "#ededed" }}>
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3
      className="mt-6 mb-2 font-display text-sm font-bold uppercase tracking-[0.14em]"
      style={{ color: "#6b93ff" }}
    >
      {children}
    </h3>
  ),
  blockquote: ({ children }) => (
    <div
      className="my-5 rounded-[var(--radius-md)] px-4 py-3"
      style={{
        background: "rgba(255,201,77,.08)",
        borderLeft: "3px solid #ffc94d",
      }}
    >
      <p
        className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
        style={{ color: "#ffc94d" }}
      >
        VERIFY
      </p>
      <div style={BODY}>{children}</div>
    </div>
  ),
  p: ({ children }) => (
    <p style={BODY} className="my-4">
      {citify(children)}
    </p>
  ),
  ul: ({ children }) => (
    <ul style={BODY} className="my-4 ml-5 list-disc space-y-2 marker:text-muted-foreground">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol style={BODY} className="my-4 ml-5 list-decimal space-y-2 marker:text-muted-foreground">
      {children}
    </ol>
  ),
  li: ({ children }) => (
    <li style={{ lineHeight: "1.72" }}>{citify(children)}</li>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold" style={{ color: "#ededed" }}>
      {citify(children)}
    </strong>
  ),
  em: ({ children }) => <em className="italic text-muted-foreground">{children}</em>,
  code: ({ children }) => (
    <code
      className="rounded-[var(--radius-sm)] bg-muted px-1.5 py-0.5 font-mono text-[0.85em]"
      style={{ color: "#6b93ff" }}
    >
      {children}
    </code>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="underline underline-offset-2"
      style={{ color: "#6b93ff", textDecorationColor: "#6b93ff" }}
    >
      {children}
    </a>
  ),
}

export default function AnswerView({ text }: { text: string }) {
  return (
    <article
      className="rounded-[var(--radius-lg)] p-6 sm:p-8"
      style={{
        background: "linear-gradient(160deg, rgba(255,255,255,.05), rgba(255,255,255,.012))",
        border: "1px solid rgba(255,255,255,.09)",
      }}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </article>
  )
}
