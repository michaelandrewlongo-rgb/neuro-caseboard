import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"
import { citify } from "@/lib/citations"
import { Card } from "@/components/ui"

// Clinical reading surface: a calm Source Serif 4 column. Inline [n] / [L#] markers become
// footnote-style chips; everything else stays static and legible (no animated clinical text).
const components: Components = {
  h2: ({ children }) => (
    <h2 className="mt-7 mb-3 font-display text-xl font-bold text-foreground">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mt-6 mb-2 font-display text-sm font-bold uppercase tracking-[0.14em] text-primary">
      {children}
    </h3>
  ),
  p: ({ children }) => <p className="reading my-4">{citify(children)}</p>,
  ul: ({ children }) => (
    <ul className="reading my-4 ml-5 list-disc space-y-2 marker:text-muted-foreground">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="reading my-4 ml-5 list-decimal space-y-2 marker:text-muted-foreground">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-[1.7]">{citify(children)}</li>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{citify(children)}</strong>,
  em: ({ children }) => <em className="italic text-muted-foreground">{children}</em>,
  code: ({ children }) => (
    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em] text-primary">
      {children}
    </code>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="text-primary underline decoration-primary underline-offset-2 hover:decoration-primary"
    >
      {children}
    </a>
  ),
}

export default function AnswerView({ text }: { text: string }) {
  return (
    <Card className="p-6 sm:p-8">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </Card>
  )
}
