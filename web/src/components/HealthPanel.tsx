import { useEffect, useState } from "react"
import { getHealth, type Health } from "@/lib/api"
import { cn } from "@/lib/utils"

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

/** Rounded accent dot with a colored glow. */
function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className="inline-block h-2 w-2 shrink-0 rounded-full"
      style={{
        background: ok ? "#34e07f" : "#ff5a5a",
        boxShadow: ok ? "0 0 7px rgba(52,224,127,.7)" : "0 0 7px rgba(255,90,90,.7)",
      }}
      aria-hidden
    />
  )
}

/** Palette-aware availability pill — sage for online, brick for absent. */
function StatusPill({ ok }: { ok: boolean }) {
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 font-mono text-[9px] font-bold uppercase"
      style={{
        background: ok ? "rgba(52,224,127,.12)" : "rgba(255,90,90,.12)",
        border: `1px solid ${ok ? "rgba(52,224,127,.28)" : "rgba(255,90,90,.28)"}`,
        borderRadius: "999px",
        color: ok ? "#34e07f" : "#ff8f8a",
        letterSpacing: "0.14em",
      }}
    >
      {ok ? "available" : "absent"}
    </span>
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
    <div className="surface p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="eyebrow">Engine availability</h2>
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          /api/health
        </span>
      </div>

      {loading && (
        <p className="flex items-center gap-2 font-mono text-sm text-muted-foreground">
          <span
            className={cn("inline-block h-1.5 w-1.5 rounded-full")}
            style={{ background: "#8a8a8a", animation: "pulse 2.4s ease-in-out infinite" }}
            aria-hidden
          />
          probing engine…
        </p>
      )}

      {/* Honest "API unreachable" error — preserved verbatim, re-skinned to palette */}
      {error && !loading && (
        <div
          className="rounded-xl p-4 text-sm"
          style={{
            background: "rgba(255,90,90,.08)",
            border: "1px solid rgba(255,90,90,.22)",
          }}
          role="alert"
        >
          <p className="font-bold" style={{ color: "#ff8f8a" }}>
            API unreachable
          </p>
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
              className="flex items-start gap-3 rounded-lg px-3.5 py-2.5"
              style={{
                background: "rgba(255,255,255,.03)",
                border: "1px solid rgba(255,255,255,.07)",
              }}
            >
              <span className="mt-1">
                <StatusDot ok={r.ok} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2.5">
                  <span className="text-sm font-semibold text-foreground">{r.label}</span>
                  <StatusPill ok={r.ok} />
                </div>
                {r.detail && (
                  <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
                    {r.detail}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
