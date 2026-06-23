import { useState } from "react"
import type { ReactNode } from "react"
import type { Dossier, DossierClaim, DossierFigure, DossierSection } from "@/lib/api"
import { type ClaimFilter, subsetClaims } from "@/lib/claimFilter"
import { summarizeDossier } from "@/lib/quant"

export type ClaimMark = "wrong" | "important"
// Re-export so existing consumers (Build.tsx) keep importing ClaimFilter from here.
export type { ClaimFilter } from "@/lib/claimFilter"

interface Rehearsal {
  rehearsal?: boolean
  markOf?: (heading: string, claim: DossierClaim) => ClaimMark | null
  onMark?: (heading: string, claim: DossierClaim, mark: ClaimMark) => void
  onMissing?: (heading: string, text: string) => void
}

// Per-status palette: sage for supported, ochre for to-verify, red for quarantined.
function statusMeta(status: DossierClaim["status"]) {
  if (status === "supported") {
    return { color: "#34e07f", label: "SUPPORTED", srLabel: "corpus-supported" } as const
  }
  if (status === "verify") {
    return { color: "#ffc94d", label: "TO VERIFY", srLabel: "needs clinician verification" } as const
  }
  return {
    color: "#ff5a5a",
    label: "QUARANTINED",
    srLabel: "off-target — excluded from synthesis",
  } as const
}

// ---------------------------------------------------------------------------
// Teal citation chip [fig_id]
// ---------------------------------------------------------------------------
function CitChip({ figId }: { figId: string }) {
  return (
    <a
      href={`#${figId}`}
      className="inline-flex items-center font-mono text-[10px] font-bold transition-colors"
      style={{
        padding: "1px 5px",
        background: "rgba(107,147,255,.12)",
        color: "#6b93ff",
        borderRadius: "5px",
        border: "1px solid rgba(107,147,255,.22)",
        textDecoration: "none",
      }}
    >
      [{figId}]
    </a>
  )
}

// ---------------------------------------------------------------------------
// Claim card
// ---------------------------------------------------------------------------
function ClaimCard({
  claim,
  heading,
  r,
}: {
  claim: DossierClaim
  heading: string
  r: Rehearsal
}) {
  const active = r.markOf?.(heading, claim) ?? null
  const meta = statusMeta(claim.status)

  return (
    <li
      className="relative flex overflow-hidden"
      style={{
        background: "rgba(255,255,255,.022)",
        border: "1px solid rgba(255,255,255,.08)",
        borderRadius: "12px",
      }}
    >
      {/* Left status bar */}
      <div
        className="w-[3px] shrink-0"
        style={{
          background: meta.color,
          boxShadow: `0 0 8px ${meta.color}`,
          borderRadius: "12px 0 0 12px",
        }}
      />

      <div className="min-w-0 flex-1 p-4">
        {/* Status eyebrow + glow dot */}
        <div className="mb-2 flex items-center gap-1.5">
          <span
            className="h-1.5 w-1.5 shrink-0 rounded-full"
            aria-hidden="true"
            style={{ background: meta.color, boxShadow: `0 0 7px ${meta.color}` }}
          />
          <span
            className="font-mono text-[9px] font-bold uppercase tracking-[0.18em]"
            style={{ color: meta.color }}
          >
            {meta.label}
          </span>
          {/* SR: state the status in words — glyph + color are not sufficient alone */}
          <span className="sr-only">({meta.srLabel})</span>
        </div>

        {/* Claim text */}
        <p className="text-[13px] leading-relaxed" style={{ color: "#ededed" }}>
          {claim.text}
        </p>

        {/* Why: line — teal "Why:" label + body text */}
        {claim.why && (
          <p className="mt-2 text-[12px] leading-relaxed" style={{ color: "#a8a8a8" }}>
            <span
              className="font-mono text-[9px] font-bold uppercase tracking-[0.12em]"
              style={{ color: "#6b93ff" }}
            >
              Why:
            </span>{" "}
            {claim.why}
          </p>
        )}

        {/* Sub-items — teal ☐ glyph (accent-color equivalent) */}
        {claim.sub_items.length > 0 && (
          <ul className="mt-2 flex flex-col gap-1" aria-label="Considerations">
            {claim.sub_items.map((s, i) => (
              <li key={i} className="flex items-start gap-2">
                <span
                  className="mt-0.5 shrink-0 font-mono text-[11px] leading-none"
                  aria-hidden="true"
                  style={{ color: "#6b93ff" }}
                >
                  ☐
                </span>
                <span className="text-[11px] leading-relaxed" style={{ color: "#a8a8a8" }}>
                  {s}
                </span>
              </li>
            ))}
          </ul>
        )}

        {/* Citation chips [fig_id] + "→ fig_id" figure links */}
        {claim.figure_ids.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {claim.figure_ids.map((fid) => (
              <CitChip key={fid} figId={fid} />
            ))}
            {claim.figure_ids.map((fid) => (
              <a
                key={`fl-${fid}`}
                href={`#${fid}`}
                className="font-mono text-[10px] transition-colors hover:underline"
                style={{ color: "#6b93ff", textDecoration: "none" }}
              >
                → {fid}
              </a>
            ))}
          </div>
        )}

        {/* Rehearsal mark controls */}
        {r.rehearsal && (
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => r.onMark?.(heading, claim, "wrong")}
              className="font-mono text-[11px] transition-colors"
              style={{
                padding: "2px 8px",
                background: active === "wrong" ? "#ff5a5a" : "rgba(255,255,255,.06)",
                color: active === "wrong" ? "#fff" : "#8a8a8a",
                borderRadius: "6px",
                border: `1px solid ${active === "wrong" ? "#ff5a5a" : "rgba(255,255,255,.09)"}`,
                cursor: "pointer",
              }}
            >
              ✗ wrong
            </button>
            <button
              type="button"
              onClick={() => r.onMark?.(heading, claim, "important")}
              className="font-mono text-[11px] transition-colors"
              style={{
                padding: "2px 8px",
                background: active === "important" ? "#ffc94d" : "rgba(255,255,255,.06)",
                color: active === "important" ? "#0a0a0a" : "#8a8a8a",
                borderRadius: "6px",
                border: `1px solid ${active === "important" ? "#ffc94d" : "rgba(255,255,255,.09)"}`,
                cursor: "pointer",
              }}
            >
              ★ important
            </button>
          </div>
        )}
      </div>
    </li>
  )
}

// ---------------------------------------------------------------------------
// Rehearsal "missing" input (preserved behavior, restyled)
// ---------------------------------------------------------------------------
function MissingInput({
  heading,
  onMissing,
}: {
  heading: string
  onMissing: (h: string, t: string) => void
}) {
  const [text, setText] = useState("")
  return (
    <form
      className="mt-3 flex gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        const t = text.trim()
        if (t) {
          onMissing(heading, t)
          setText("")
        }
      }}
    >
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={`Missing from ${heading}…`}
        className="field flex-1 !py-1.5 text-sm"
      />
      <button
        type="submit"
        className="font-mono text-[11px] transition-colors"
        style={{
          padding: "4px 10px",
          background: "rgba(107,147,255,.15)",
          color: "#6b93ff",
          borderRadius: "7px",
          border: "1px solid rgba(107,147,255,.28)",
          cursor: "pointer",
        }}
      >
        + missing
      </button>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Section letter badge (neutral white tile, near-black letter — A / B / C…)
// ---------------------------------------------------------------------------
function LetterBadge({ letter }: { letter: string }) {
  return (
    <div
      className="flex h-8 w-8 shrink-0 items-center justify-center font-display text-sm font-bold"
      style={{
        background: "#ededed",
        color: "#0a0a0a",
        borderRadius: "8px",
      }}
    >
      {letter}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Section card
// ---------------------------------------------------------------------------
function SectionCard({
  section,
  sectionIdx,
  r,
  filter,
}: {
  section: DossierSection
  sectionIdx: number
  r: Rehearsal
  filter: ClaimFilter
}) {
  const letter = String.fromCharCode(65 + sectionIdx) // A, B, C …
  const visible = subsetClaims(section.claims, filter)
  // A non-"all" tab strictly subsets the page: hide the whole section (header, intro,
  // rehearsal input) when it has no claims in the active filter. Under "all", always
  // render the section even if it carries no claims (preserves prior behavior).
  if (filter !== "all" && visible.length === 0) return null
  return (
    <div
      className="reveal p-5"
      style={{
        background: "rgba(255,255,255,.022)",
        border: "1px solid rgba(255,255,255,.08)",
        borderRadius: "16px",
        animationDelay: `${sectionIdx * 0.06}s`,
      }}
    >
      {/* Section header: letter badge + heading */}
      <div className="mb-3 flex items-center gap-3">
        <LetterBadge letter={letter} />
        <h2 className="font-display text-base font-semibold" style={{ color: "#ededed" }}>
          {section.heading}
        </h2>
      </div>

      {/* Intro paragraph */}
      {section.intro && (
        <p className="mb-4 text-[12px] leading-relaxed" style={{ color: "#a8a8a8" }}>
          {section.intro}
        </p>
      )}

      {/* Claims list — strict subset of the active filter */}
      {visible.length > 0 && (
        <ul className="flex flex-col gap-3">
          {visible.map((c, i) => (
            <ClaimCard key={i} claim={c} heading={section.heading} r={r} />
          ))}
        </ul>
      )}

      {/* Rehearsal: missing-consideration input */}
      {r.rehearsal && r.onMissing && (
        <MissingInput heading={section.heading} onMissing={r.onMissing} />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Figure card (right rail)
// ---------------------------------------------------------------------------
function FigureCard({ fig }: { fig: DossierFigure }) {
  const show = fig.image_url && fig.image_available
  return (
    <figure
      id={fig.fig_id}
      className="scroll-mt-24 overflow-hidden transition-transform hover:-translate-y-0.5"
      style={{
        background: "rgba(255,255,255,.022)",
        border: "1px solid rgba(255,255,255,.08)",
        borderRadius: "10px",
      }}
    >
      <div
        className="flex aspect-[4/3] items-center justify-center"
        style={
          show
            ? undefined
            : {
                background:
                  "repeating-linear-gradient(45deg,rgba(255,255,255,.02) 0px,rgba(255,255,255,.02) 1px,transparent 1px,transparent 8px)",
                borderBottom: "1px dashed rgba(255,255,255,.10)",
              }
        }
      >
        {show ? (
          <img
            src={fig.image_url!}
            alt={fig.caption || fig.citation}
            loading="lazy"
            className="h-full w-full object-contain"
          />
        ) : (
          <div className="flex flex-col items-center gap-1 px-3 text-center">
            <span
              className="font-mono text-[9px] font-bold uppercase tracking-[0.18em]"
              style={{ color: "#6b93ff" }}
            >
              {fig.fig_id}
            </span>
            <span className="font-mono text-[9px]" style={{ color: "#666666" }}>
              image unavailable
            </span>
          </div>
        )}
      </div>
      <figcaption className="p-2.5 space-y-0.5">
        <span
          className="block font-mono text-[9px] font-bold uppercase tracking-[0.14em]"
          style={{ color: "#6b93ff" }}
        >
          {fig.fig_id} · {fig.citation}
        </span>
        {fig.caption && (
          <p className="text-[11px] leading-snug" style={{ color: "#a8a8a8" }}>
            {fig.caption}
          </p>
        )}
        {fig.claim_ref && (
          <p className="font-mono text-[9px]" style={{ color: "#666666" }}>
            <span className="uppercase tracking-wider">supports:</span> {fig.claim_ref}
          </p>
        )}
      </figcaption>
    </figure>
  )
}

// ---------------------------------------------------------------------------
// Right-rail section panel
// ---------------------------------------------------------------------------
function RailPanel({
  title,
  titleColor = "#6b93ff",
  children,
}: {
  title: string
  titleColor?: string
  children: ReactNode
}) {
  return (
    <div
      className="p-4"
      style={{
        background: "rgba(255,255,255,.018)",
        border: "1px solid rgba(255,255,255,.07)",
        borderRadius: "14px",
      }}
    >
      <h3
        className="mb-3 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
        style={{ color: titleColor }}
      >
        {title}
      </h3>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// DossierView — default export
// Adds `filter` prop (default "all") without breaking Build.tsx's existing call.
// ---------------------------------------------------------------------------
export default function DossierView({
  dossier,
  filter = "all",
  ...r
}: { dossier: Dossier; filter?: ClaimFilter } & Rehearsal) {
  // Aggregate right-rail data from real fields — no fabrication
  const allFigures = dossier.sections.flatMap((s) => s.figures)
  const allCrossRefs = dossier.sections.flatMap((s) => s.cross_refs).filter(Boolean)
  const appendix = dossier.appendix.entries
  const railEmpty = allFigures.length === 0 && allCrossRefs.length === 0 && appendix.length === 0

  // BACKLOG P5 #15: quantitative outcome summary — numbers literally present in the dossier's
  // claims (rates, denominators, CIs, p-values, follow-up). Never fabricated.
  const { metrics: quantMetrics, counts: quantCounts } = summarizeDossier(
    dossier.sections.flatMap((s) =>
      s.claims.map((c) => ({ text: `${c.text} ${c.why}`, context: c.text })),
    ),
  )

  // Under a non-"all" filter every SectionCard with no matching claim returns null; if NONE match
  // across all sections the main column would go blank, so render an explicit empty-state instead.
  const anyVisible = dossier.sections.some((s) => subsetClaims(s.claims, filter).length > 0)

  return (
    <div
      className="grid gap-6"
      style={{ gridTemplateColumns: "minmax(0,1fr) 372px" }}
    >
      {/* ── Main column: section cards ── */}
      <div className="flex min-w-0 flex-col gap-4">
        {/* By the numbers — quantitative outcome summary (P5 #15) */}
        {quantMetrics.length > 0 && (
          <section className="surface p-4" aria-label="Quantitative outcome summary">
            <p className="eyebrow mb-2">By the numbers</p>
            <p className="mb-3 font-mono text-[11px] text-muted-foreground">
              {Object.entries(quantCounts)
                .map(([k, n]) => `${k}: ${n}`)
                .join("  ·  ")}
              {"  ·  hover a value for its source claim"}
            </p>
            <div className="flex flex-wrap gap-2">
              {quantMetrics.map((m, i) => (
                <span
                  key={i}
                  className="rounded-md px-2 py-0.5 font-mono text-xs font-semibold"
                  style={{ background: "rgba(107,147,255,.12)", color: "#6b93ff" }}
                  title={m.context}
                >
                  {m.value}
                  {/* a11y: `title` is mouse-only and aria-label is name-prohibited on a
                      generic <span>; an sr-only companion is read during DOM traversal so the
                      source-claim grounding reaches screen-reader users too. */}
                  {m.context && <span className="sr-only"> — {m.context}</span>}
                </span>
              ))}
            </div>
          </section>
        )}
        {dossier.sections.map((s, i) => (
          <SectionCard key={i} section={s} sectionIdx={i} r={r} filter={filter} />
        ))}
        {/* Empty-state: a non-"all" filter that matches nothing in any section leaves the column
            blank otherwise. Mirrors the muted-mono rail empty state. */}
        {filter !== "all" && !anyVisible && (
          <div
            className="flex items-center justify-center p-6"
            style={{
              background: "rgba(255,255,255,.018)",
              border: "1px dashed rgba(255,255,255,.07)",
              borderRadius: "14px",
            }}
          >
            <p
              className="font-mono text-[10px] uppercase tracking-[0.14em]"
              style={{ color: "#666666" }}
            >
              No claims match this filter
            </p>
          </div>
        )}
      </div>

      {/* ── Right rail ── */}
      <aside className="flex flex-col gap-4">
        {/* Figures */}
        {allFigures.length > 0 && (
          <RailPanel title="Figures">
            <div className="flex flex-col gap-3">
              {allFigures.map((f) => (
                <FigureCard key={f.fig_id} fig={f} />
              ))}
            </div>
          </RailPanel>
        )}

        {/* Corpus sources — from section cross_refs */}
        {allCrossRefs.length > 0 && (
          <RailPanel title="Corpus sources">
            <ul className="flex flex-col gap-2">
              {allCrossRefs.map((ref, i) => (
                <li key={i} className="flex items-baseline gap-1.5">
                  <span
                    className="inline-flex shrink-0 items-center font-mono text-[9px] font-bold"
                    style={{
                      padding: "1px 4px",
                      background: "rgba(107,147,255,.12)",
                      color: "#6b93ff",
                      borderRadius: "4px",
                      border: "1px solid rgba(107,147,255,.2)",
                    }}
                  >
                    [{i + 1}]
                  </span>
                  <span className="text-[11px] leading-snug" style={{ color: "#a8a8a8" }}>
                    {ref}
                  </span>
                </li>
              ))}
            </ul>
          </RailPanel>
        )}

        {/* Contemporary literature (plum) — from appendix entries */}
        {appendix.length > 0 && (
          <RailPanel title="Contemporary literature" titleColor="#ff66d8">
            <div className="flex flex-col gap-3">
              {appendix.map((entry, ei) => (
                <div key={ei}>
                  {entry.heading && (
                    <p
                      className="mb-1.5 font-mono text-[9px] font-bold uppercase tracking-[0.14em]"
                      style={{ color: "#ff8fe2" }}
                    >
                      {entry.heading}
                    </p>
                  )}
                  <ul className="flex flex-col gap-1">
                    {entry.items.map((item, ii) => (
                      <li key={ii} className="flex items-baseline gap-1.5">
                        <span
                          className="inline-flex shrink-0 items-center font-mono text-[9px] font-bold"
                          style={{
                            padding: "1px 4px",
                            background: "rgba(255,102,216,.12)",
                            color: "#ff66d8",
                            borderRadius: "4px",
                            border: "1px solid rgba(255,102,216,.2)",
                          }}
                        >
                          [L{ii + 1}]
                        </span>
                        <span className="text-[11px] leading-snug" style={{ color: "#a8a8a8" }}>
                          {item}
                        </span>
                      </li>
                    ))}
                    {entry.sources.map((src, si) => (
                      <li key={`s${si}`} className="flex items-baseline gap-1.5">
                        <span
                          className="inline-flex shrink-0 items-center font-mono text-[9px] font-bold"
                          style={{
                            padding: "1px 4px",
                            background: "rgba(255,102,216,.12)",
                            color: "#ff66d8",
                            borderRadius: "4px",
                            border: "1px solid rgba(255,102,216,.2)",
                          }}
                        >
                          [L{entry.items.length + si + 1}]
                        </span>
                        <span className="text-[11px] leading-snug" style={{ color: "#a8a8a8" }}>
                          {src}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </RailPanel>
        )}

        {/* Empty rail state — honest degradation */}
        {railEmpty && (
          <div
            className="flex items-center justify-center p-6"
            style={{
              background: "rgba(255,255,255,.018)",
              border: "1px dashed rgba(255,255,255,.07)",
              borderRadius: "14px",
            }}
          >
            <p
              className="font-mono text-[10px] uppercase tracking-[0.14em]"
              style={{ color: "#666666" }}
            >
              No figures or sources
            </p>
          </div>
        )}
      </aside>
    </div>
  )
}
