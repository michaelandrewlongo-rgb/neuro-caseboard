import { Children, type ReactNode } from "react"
import { cn } from "@/lib/utils"

const MARKER = /(\[L?\d+\])/g

function chipify(text: string): ReactNode[] {
  return text.split(MARKER).map((part, i) => {
    const m = /^\[(L?)(\d+)\]$/.exec(part)
    if (!m) return part
    const isLit = m[1] === "L"
    return (
      <sup
        key={i}
        className={cn(
          "mx-px inline-flex items-center border-2 border-border px-1 align-super font-mono text-[0.6em] font-bold leading-none",
          isLit ? "bg-accent text-accent-foreground" : "bg-secondary text-foreground",
        )}
      >
        {part.slice(1, -1)}
      </sup>
    )
  })
}

/** Wrap [n] / [L#] citation markers in string text nodes with footnote-style chips. Only touches
    plain-string children, so it never disturbs markdown structure. */
export function citify(children: ReactNode): ReactNode {
  return Children.map(children, (child) =>
    typeof child === "string" ? chipify(child) : child,
  )
}
