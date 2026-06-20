import { Children, type ReactNode } from "react"
import { splitCitations, PROVENANCE_LABEL, type Provenance } from "@/lib/provenance"

// Distinct pill colours by provenance: teal = textbook corpus [n], plum = PubMed [L#],
// ochre = personal card [C#]. Each pill links to its matching source-list entry (jump-to-source).
const PILL_STYLE: Record<Provenance, { background: string; color: string }> = {
  textbook: { background: "rgba(107,147,255,.12)", color: "#6b93ff" },
  literature: { background: "rgba(255,102,216,.15)", color: "#ff8fe2" },
  card: { background: "rgba(255,201,77,.15)", color: "#ffc94d" },
}

function chipify(text: string): ReactNode[] {
  return splitCitations(text).map((seg, i) => {
    if ("text" in seg) return seg.text
    const { kind, label, anchor } = seg.marker
    return (
      <a
        key={i}
        href={`#${anchor}`}
        title={PROVENANCE_LABEL[kind]}
        aria-label={`${PROVENANCE_LABEL[kind]} ${label} — jump to source`}
        style={PILL_STYLE[kind]}
        className="mx-px inline-flex cursor-pointer items-center rounded-[7px] px-[5px] py-px align-super font-mono text-[0.63em] font-semibold leading-none no-underline"
      >
        {label}
      </a>
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
