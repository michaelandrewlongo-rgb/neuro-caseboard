import type {
  OperativeBriefing,
  BriefingSection,
  TreatmentModality,
  EquipmentPlan,
  DecisionAlgorithm,
} from "@/lib/api"

// The one-page operative briefing preview (spec §1/§11): NO inline figures, NO visible [T#]/[L#]
// markers — source_refs stay hidden; the gallery + references are separate surfaces below.

function Section({ section }: { section: BriefingSection }) {
  const items = section.items ?? []
  if (!items.length && !section.note) return null
  return (
    <div className="border-t border-border pt-3">
      <h3 className="font-display text-sm font-bold uppercase tracking-wide text-foreground">{section.title}</h3>
      <ul className="mt-2 flex flex-col gap-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2 text-sm leading-relaxed text-foreground">
            <span aria-hidden className="select-none text-secondary">—</span>
            <span>
              {it.text}
              {it.unsupported && (
                <span className="ml-2 font-mono text-[10px] uppercase tracking-wide text-amber">
                  clinician-verify
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
      {section.note && <p className="mt-1.5 text-xs italic text-muted-foreground">{section.note}</p>}
    </div>
  )
}

function Algorithm({ algo }: { algo: DecisionAlgorithm }) {
  const nodes = algo.nodes ?? []
  if (!nodes.length) return null
  const label = (id: string) => nodes.find((n) => n.id === id)?.label ?? id
  const ids = new Set(nodes.map((n) => n.id))
  const edges = (algo.edges ?? []).filter((e) => ids.has(e.src) && ids.has(e.dst))
  const sources = nodes.filter((n) => edges.some((e) => e.src === n.id))
  if (!sources.length) return null
  return (
    <div className="border-t border-border pt-3">
      <h3 className="font-display text-sm font-bold uppercase tracking-wide text-foreground">Decision algorithm</h3>
      <div className="mt-2 flex flex-col gap-2">
        {sources.map((n) => (
          <div key={n.id} className="rounded-md border border-border bg-muted p-2.5">
            <p className="text-sm font-semibold text-foreground">{n.label}</p>
            <ul className="mt-1 flex flex-col gap-0.5">
              {edges
                .filter((e) => e.src === n.id)
                .map((e, i) => (
                  <li key={i} className="font-mono text-xs text-muted-foreground">
                    {e.condition ? <span className="text-secondary">{e.condition} → </span> : "→ "}
                    {label(e.dst)}
                  </li>
                ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

function Modalities({ mods }: { mods: TreatmentModality[] }) {
  if (!mods.length) return null
  return (
    <div className="border-t border-border pt-3">
      <h3 className="font-display text-sm font-bold uppercase tracking-wide text-foreground">Treatment options</h3>
      <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {mods.map((m, i) => (
          <div
            key={i}
            className={`rounded-md border bg-muted p-3 ${m.preferred ? "border-success" : "border-border"}`}
          >
            <p className="text-sm font-bold text-foreground">
              {m.name}
              {m.preferred && <span className="ml-2 font-mono text-[10px] uppercase text-success">preferred</span>}
            </p>
            {m.role && <p className="mt-0.5 text-xs text-muted-foreground">{m.role}</p>}
            <ul className="mt-1.5 flex flex-col gap-0.5 text-xs text-foreground">
              {(m.advantages ?? []).map((a, j) => (
                <li key={`a${j}`}>+ {a}</li>
              ))}
              {(m.limitations ?? []).map((l, j) => (
                <li key={`l${j}`} className="text-muted-foreground">
                  − {l}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

function Equipment({ equipment }: { equipment: EquipmentPlan }) {
  // Generic: render every non-empty string-list field; skip discriminator + source_refs.
  const rows = Object.entries(equipment).filter(
    ([k, v]) => k !== "kind" && k !== "source_refs" && Array.isArray(v) && v.length,
  ) as [string, string[]][]
  if (!rows.length) return null
  const human = (k: string) => k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  return (
    <div className="border-t border-border pt-3">
      <h3 className="font-display text-sm font-bold uppercase tracking-wide text-foreground">
        Equipment · {equipment.kind}
      </h3>
      <div className="mt-2 flex flex-col gap-1.5">
        {rows.map(([k, vals]) => (
          <div key={k} className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
            <span className="shrink-0 font-mono text-xs font-semibold text-muted-foreground sm:w-44">{human(k)}</span>
            <span className="text-sm text-foreground">{vals.join("; ")}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function OperativeBriefingView({ briefing }: { briefing: OperativeBriefing }) {
  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-5">
      <div>
        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-secondary">
          Operative Briefing
        </p>
        <h2 className="mt-1 font-display text-2xl font-bold tracking-tight text-foreground">{briefing.title}</h2>
      </div>
      {(briefing.sections ?? []).map((s) => (
        <Section key={s.key} section={s} />
      ))}
      {briefing.algorithm && <Algorithm algo={briefing.algorithm} />}
      <Modalities mods={briefing.modalities ?? []} />
      {briefing.equipment && <Equipment equipment={briefing.equipment} />}
      {(briefing.unknowns ?? []).length > 0 && (
        <div className="border-l-2 border-amber pl-3 text-xs text-muted-foreground">
          <span className="font-bold text-foreground">Case-specific unknowns: </span>
          {(briefing.unknowns ?? []).join(" · ")}
        </div>
      )}
      {briefing.disclaimer && (
        <p className="border-t border-border pt-3 font-mono text-[10px] text-muted-foreground">{briefing.disclaimer}</p>
      )}
    </div>
  )
}
