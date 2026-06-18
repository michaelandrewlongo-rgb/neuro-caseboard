import { useEffect, useState } from "react"
import { getHealth, type Health } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Card, Badge } from "@/components/ui"

type Row = { key: string; label: string; ok: boolean; detail?: string | null }

function rowsFromHealth(h: Health): Row[] {
  return [
    { key: "engine", label: "Engine", ok: h.engine, detail: h.detail.engine.error },
    {
      key: "synth",
      label: "Synthesis · Vertex",
      ok: h.synth,
      detail: h.synth
        ? `${h.detail.synth.provider} · ${h.detail.synth.project ?? "no project"}`
        : h.detail.synth.detail,
    },
    {
      key: "corpus",
      label: "Textbook retrieval",
      ok: h.corpus,
      detail: h.corpus ? h.detail.corpus.index_dir : h.detail.corpus.detail,
    },
    {
      key: "cards",
      label: "Board-review cards",
      ok: h.cards_index,
      detail: h.cards_index ? h.detail.cards.table : h.detail.cards.detail,
    },
    {
      key: "ncbi",
      label: "PubMed literature · NCBI key",
      ok: h.ncbi_key,
      detail: h.detail.literature.detail,
    },
  ]
}

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      className={cn(
        "inline-block h-2.5 w-2.5 shrink-0 border-2 border-border",
        ok ? "bg-[var(--color-success)]" : "bg-primary",
      )}
      aria-hidden
    />
  )
}

export default function HealthPanel() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const ctrl = new AbortController()
    getHealth(ctrl.signal)
      .then((h) => {
        setHealth(h)
        setError(null)
      })
      .catch((e) => {
        if (e?.name !== "AbortError") setError(String(e?.message ?? e))
      })
      .finally(() => setLoading(false))
    return () => ctrl.abort()
  }, [])

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="eyebrow">Engine availability</h2>
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          /api/health
        </span>
      </div>

      {loading && <p className="font-mono text-sm text-muted-foreground">probing engine…</p>}

      {error && !loading && (
        <div className="border-2 border-border bg-secondary p-4 text-sm">
          <p className="font-bold text-foreground">API unreachable</p>
          <p className="mt-1 text-muted-foreground">{error}</p>
          <p className="mt-2 font-mono text-xs text-muted-foreground">
            Is the engine wrapper running on :8001? Start it with the dev command.
          </p>
        </div>
      )}

      {health && !loading && (
        <ul className="flex flex-col gap-2">
          {rowsFromHealth(health).map((r) => (
            <li
              key={r.key}
              className="flex items-start gap-3 border-2 border-border bg-card px-3.5 py-2.5"
            >
              <span className="mt-1">
                <Dot ok={r.ok} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2.5">
                  <span className="text-sm font-bold text-foreground">{r.label}</span>
                  <Badge tone={r.ok ? "success" : "signal"}>{r.ok ? "available" : "absent"}</Badge>
                </div>
                {r.detail && (
                  <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">{r.detail}</p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
