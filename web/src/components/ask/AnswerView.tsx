import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"

// Clinical reading surface: legible, static (no animated text), dark-theme markdown. The engine's
// inline [n] / [L#] citation markers are preserved verbatim and resolve to the Sources / Literature
// panels below.
const components: Components = {
  h2: ({ children }) => (
    <h2 className="mt-6 mb-2 font-display text-xl font-bold text-ink">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mt-5 mb-2 font-display text-base font-semibold tracking-wide text-teal">
      {children}
    </h3>
  ),
  p: ({ children }) => <p className="my-3 leading-relaxed text-ink">{children}</p>,
  ul: ({ children }) => <ul className="my-3 ml-5 list-disc space-y-1.5 text-ink">{children}</ul>,
  ol: ({ children }) => <ol className="my-3 ml-5 list-decimal space-y-1.5 text-ink">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed marker:text-ink-faint">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  em: ({ children }) => <em className="italic text-ink-dim">{children}</em>,
  code: ({ children }) => (
    <code className="rounded bg-navy-800 px-1.5 py-0.5 font-mono text-[0.85em] text-teal">
      {children}
    </code>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="text-teal underline decoration-teal/40 underline-offset-2 hover:decoration-teal"
    >
      {children}
    </a>
  ),
}

export default function AnswerView({ text }: { text: string }) {
  return (
    <article className="rounded-xl border border-navy-700/60 bg-navy-900/40 p-6">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </article>
  )
}
