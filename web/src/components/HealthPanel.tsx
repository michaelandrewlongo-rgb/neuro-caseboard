import { useEffect, useState } from "react"
import { getHealth, type Health } from "@/lib/api"
import { cn } from "@/lib/utils"

type Row = { key: string; label: string; ok: boolean; detail?: string | null }

function rowsFromHealth(h: Health): Row[] {
  return [
    { key: "engine", label: "Engine", ok: h.engine, detail: h.detail.engine.error },
    {
      key: "synth",
      label: "Synthesis (Vertex)",
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
      label: "PubMed literature (NCBI key)",
      ok: h.ncbi_key,
      detail: h.detail.literature.detail,
    },
  ]
}

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      className={cn(
        "inline-block h-2.5 w-2.5 shrink-0 rounded-full",
        ok ? "bg-teal shadow-[0_0_8px_var(--color-teal)]" : "bg-signal",
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
    <section className="rounded-xl border border-navy-700/60 bg-navy-900/60 p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink-faint">
          Engine availability
        </h2>
        <span className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
          /api/health
        </span>
      </div>

      {loading && (
        <p className="font-mono text-sm text-ink-dim">probing engine…</p>
      )}

      {error && !loading && (
        <div className="rounded-md border border-signal/40 bg-signal/10 p-3 text-sm text-ink">
          <p className="font-medium text-signal">API unreachable</p>
          <p className="mt-1 text-ink-dim">{error}</p>
          <p className="mt-2 font-mono text-xs text-ink-faint">
            Is the engine wrapper running on :8001? Start it with the dev command.
          </p>
        </div>
      )}

      {health && !loading && (
        <ul className="flex flex-col gap-2">
          {rowsFromHealth(health).map((r) => (
            <li
              key={r.key}
              className="flex items-start gap-3 rounded-md bg-navy-850/60 px-3 py-2"
            >
              <span className="mt-1.5">
                <Dot ok={r.ok} />
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-ink">{r.label}</span>
                  <span
                    className={cn(
                      "font-mono text-[10px] uppercase tracking-wider",
                      r.ok ? "text-teal" : "text-signal",
                    )}
                  >
                    {r.ok ? "available" : "absent"}
                  </span>
                </div>
                {r.detail && (
                  <p className="truncate font-mono text-xs text-ink-faint">{r.detail}</p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
