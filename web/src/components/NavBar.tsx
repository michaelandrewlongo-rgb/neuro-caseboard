import { useEffect, useState } from "react"
import { NavLink, useNavigate } from "react-router-dom"
import { cn } from "@/lib/utils"
import { getHealth, type Health } from "@/lib/api"

// ── Route definitions ─────────────────────────────────────────────────────────
// Ask → /ask, Dossier → /build, Cards → /cards  (labels match the design spec)
const NAV_LINKS = [
  { to: "/ask",   label: "Ask" },
  { to: "/build", label: "Dossier" },
  { to: "/cards", label: "Cards" },
]

// ── Diamond logo mark ─────────────────────────────────────────────────────────
// Crimson gradient square with a rotated inner-square cutout producing a
// diamond-window effect — pure CSS, no SVG dependency.
function DiamondMark() {
  return (
    <div
      className="relative h-8 w-8 shrink-0 overflow-hidden"
      style={{
        background: "linear-gradient(135deg,#d8413a,#ff7363)",
        borderRadius: "5px",
      }}
      aria-hidden
    >
      {/* Rotated cutout — reveals the charcoal background through the centre */}
      <div
        className="absolute inset-[6px] rotate-45 bg-background"
        style={{ borderRadius: "2px" }}
      />
    </div>
  )
}

// ── Health-status derivation ──────────────────────────────────────────────────
type HealthStatus = "loading" | "online" | "degraded" | "offline"

function deriveStatus(h: Health): HealthStatus {
  if (!h.engine) return "offline"
  if (h.corpus && h.synth) return "online"
  return "degraded"
}

interface PillCfg {
  label: string
  dotColor: string
  pillBg: string
  pillBorder: string
  textColor: string
  pulse: boolean
}

function pillCfg(status: HealthStatus): PillCfg {
  switch (status) {
    case "online":
      return {
        label: "ENGINE ONLINE",
        dotColor: "#5fa86f",
        pillBg: "rgba(95,168,111,.10)",
        pillBorder: "rgba(95,168,111,.28)",
        textColor: "#74c084",
        pulse: true,
      }
    case "degraded":
      return {
        label: "ENGINE DEGRADED",
        dotColor: "#d89a3f",
        pillBg: "rgba(216,154,63,.08)",
        pillBorder: "rgba(216,154,63,.28)",
        textColor: "#e0a86a",
        pulse: false,
      }
    case "offline":
      return {
        label: "ENGINE OFFLINE",
        dotColor: "#c0564f",
        pillBg: "rgba(192,86,79,.10)",
        pillBorder: "rgba(192,86,79,.30)",
        textColor: "#d98a82",
        pulse: false,
      }
    default: // "loading"
      return {
        label: "SYNCING",
        dotColor: "#978d86",
        pillBg: "rgba(255,255,255,.04)",
        pillBorder: "rgba(255,255,255,.09)",
        textColor: "#978d86",
        pulse: false,
      }
  }
}

// ── ENGINE ONLINE / DEGRADED / OFFLINE pill ───────────────────────────────────
function HealthPill({ status }: { status: HealthStatus }) {
  const cfg = pillCfg(status)
  return (
    <div
      className="flex items-center gap-1.5 px-3 py-1"
      style={{
        background: cfg.pillBg,
        border: `1px solid ${cfg.pillBorder}`,
        borderRadius: "999px",
      }}
      role="status"
      aria-live="polite"
    >
      {/* Pulsing status dot — pulse keyframe defined in index.css */}
      <span
        className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
        style={{
          background: cfg.dotColor,
          boxShadow: `0 0 6px ${cfg.dotColor}`,
          animation: cfg.pulse ? "pulse 2.4s ease-in-out infinite" : "none",
        }}
        aria-hidden
      />
      <span
        className="font-mono text-[9px] font-bold uppercase"
        style={{ letterSpacing: "0.16em", color: cfg.textColor }}
      >
        {cfg.label}
      </span>
      {/* Accessible label for screen readers */}
      <span className="sr-only">
        Engine status:{" "}
        {status === "loading" ? "checking" : status}
      </span>
    </div>
  )
}

// ── NavBar ────────────────────────────────────────────────────────────────────
export default function NavBar() {
  const navigate = useNavigate()

  // Fetch health once on mount — same pattern as HealthPanel, no new mechanism
  const [health, setHealth]       = useState<Health | null>(null)
  const [healthError, setHealthError] = useState(false)
  const [healthLoading, setHealthLoading] = useState(true)

  useEffect(() => {
    const ctrl = new AbortController()
    getHealth(ctrl.signal)
      .then((h) => { setHealth(h); setHealthError(false) })
      .catch((e) => { if (e?.name !== "AbortError") setHealthError(true) })
      .finally(() => setHealthLoading(false))
    return () => ctrl.abort()
  }, [])

  const healthStatus: HealthStatus = healthLoading
    ? "loading"
    : healthError || !health
      ? "offline"
      : deriveStatus(health)

  return (
    <header
      className="site-header sticky top-0 z-30"
      style={{
        background:
          "linear-gradient(160deg,rgba(255,255,255,.05),rgba(255,255,255,.012))",
        borderBottom: "1px solid rgba(255,255,255,.09)",
        backdropFilter: "blur(14px)",
      }}
    >
      <nav className="mx-auto flex max-w-6xl items-center gap-4 px-6 py-3">

        {/* ── Left: diamond logo + wordmark + TELEMETRY CONSOLE tag ── */}
        <NavLink
          to="/"
          className="flex shrink-0 items-center gap-2.5"
          aria-label="Neuro·Caseboard home"
        >
          <DiamondMark />
          <div className="flex flex-col leading-none">
            <span className="font-display text-base font-semibold tracking-tight text-foreground">
              Neuro<span style={{ color: "#ff7363" }}>·</span>Caseboard
            </span>
            <span
              className="font-mono font-bold uppercase text-muted-foreground"
              style={{ fontSize: "9px", letterSpacing: "0.18em" }}
            >
              Telemetry Console
            </span>
          </div>
        </NavLink>

        {/* ── Nav buttons: Ask / Dossier / Cards (active = teal pill) ── */}
        <ul className="flex shrink-0 items-center gap-1" role="list">
          {NAV_LINKS.map((l) => (
            <li key={l.to}>
              <NavLink
                to={l.to}
                className={({ isActive }) =>
                  cn(
                    "inline-block rounded-full border px-3.5 py-1.5 font-mono text-[11px] font-bold uppercase tracking-[0.14em] transition-colors duration-150",
                    isActive
                      ? "border-[rgba(63,150,144,.32)] bg-[rgba(63,150,144,.14)] text-[#6fc0b8]"
                      : "border-transparent text-muted-foreground hover:text-foreground",
                  )
                }
              >
                {l.label}
              </NavLink>
            </li>
          ))}
        </ul>

        {/* ── Center: "Ask the corpus" command field with ⌘K hint ── */}
        <button
          type="button"
          onClick={() => navigate("/ask")}
          className={cn(
            "mx-auto flex max-w-[280px] flex-1 items-center gap-2.5 px-3.5 py-2 text-left",
            "transition-colors duration-150 hover:border-[rgba(255,255,255,.16)]",
          )}
          style={{
            background: "rgba(255,255,255,.04)",
            border: "1px solid rgba(255,255,255,.09)",
            borderRadius: "8px",
          }}
          aria-label="Open Ask — search the corpus (⌘K)"
        >
          {/* Search glyph */}
          <svg
            width="13"
            height="13"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="shrink-0 text-muted-foreground"
            aria-hidden
          >
            <circle cx="7" cy="7" r="5" />
            <line x1="11" y1="11" x2="15" y2="15" />
          </svg>
          <span className="flex-1 font-sans text-sm text-muted-foreground">
            Ask the corpus…
          </span>
          <kbd
            className="font-mono text-[10px] text-muted-foreground"
            style={{
              background: "rgba(255,255,255,.07)",
              border: "1px solid rgba(255,255,255,.11)",
              borderRadius: "4px",
              padding: "1px 5px",
            }}
          >
            ⌘K
          </kbd>
        </button>

        {/* ── Right: ENGINE ONLINE pill + avatar ── */}
        <div className="flex shrink-0 items-center gap-3">
          <HealthPill status={healthStatus} />

          {/* Avatar — initials placeholder */}
          <div
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
            style={{
              background: "rgba(255,255,255,.08)",
              border: "1px solid rgba(255,255,255,.13)",
            }}
            aria-label="User"
            role="img"
          >
            <span
              className="font-mono text-[10px] font-bold text-muted-foreground"
              aria-hidden
            >
              N
            </span>
          </div>
        </div>
      </nav>
    </header>
  )
}
