import { Children, type ReactNode } from "react"

const MARKER = /(\[L?\d+\])/g

// Teal pills for corpus [n] citations; plum pills for contemporary [L#] literature markers.
function chipify(text: string): ReactNode[] {
  return text.split(MARKER).map((part, i) => {
    const m = /^\[(L?)(\d+)\]$/.exec(part)
    if (!m) return part
    const isLit = m[1] === "L"
    return (
      <sup
        key={i}
        style={
          isLit
            ? { background: "rgba(150,120,170,.15)", color: "#c4b0d8" }
            : { background: "rgba(63,150,144,.12)", color: "#6fc0b8" }
        }
        className="mx-px inline-flex cursor-default items-center rounded-[7px] px-[5px] py-px align-super font-mono text-[0.63em] font-semibold leading-none"
      >
        {part.slice(1, -1)}
      </sup>
    )
  })
}

/** Wrap [n] / [L#] citation markers in string text nodes with teal/plum footnote pills.
    Only touches plain-string children, so it never disturbs markdown structure. */
export function citify(children: ReactNode): ReactNode {
  return Children.map(children, (child) =>
    typeof child === "string" ? chipify(child) : child,
  )
}
