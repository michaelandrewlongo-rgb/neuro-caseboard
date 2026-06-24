import { useEffect, useState } from "react"
import { NavLink, useNavigate, useLocation } from "react-router-dom"
import { cn } from "@/lib/utils"
import { isCmdK } from "@/lib/keys"
import { getHealth, type Health } from "@/lib/api"
import { shouldShowNavSearch } from "@/lib/navSearch"

// ── Route definitions ─────────────────────────────────────────────────────────
// Ask → /ask, Dossier → /build, Cards → /cards  (labels match the design spec)
const NAV_LINKS = [
  { to: "/ask",   label: "Ask" },
  { to: "/build", label: "Dossier" },
  { to: "/cards", label: "Cards" },
]

// ── Brain logo mark ───────────────────────────────────────────────────────────
// Neutral hemispheric brain glyph inside a dark rounded tile — matches the
// Neurosurgery·Signal header on the landing and the design reference.
function BrainMark() {
  return (
    <div
      className="relative grid h-8 w-8 shrink-0 place-items-center"
      style={{
        background: "#0a0a0a",
        border: "1px solid rgba(255,255,255,0.14)",
        borderRadius: "9px",
      }}
      aria-hidden
    >
      <svg
        width="18"
        height="18"
        viewBox="0 0 100 100"
        fill="none"
        stroke="#ededed"
        strokeWidth="6"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M38,18 C20,20 14,40 22,52 C12,60 16,80 34,82 C44,90 60,88 64,78 C82,78 86,58 78,48 C86,38 80,18 60,18 C54,12 44,12 38,18 Z" />
        <path d="M50,16 L50,84" opacity="0.55" />
      </svg>
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
        dotColor: "#34e07f",
        pillBg: "rgba(52,224,127,.10)",
        pillBorder: "rgba(52,224,127,.28)",
        textColor: "#34e07f",
        pulse: true,
      }
    case "degraded":
      return {
        label: "ENGINE DEGRADED",
        dotColor: "#ffc94d",
        pillBg: "rgba(255,201,77,.08)",
        pillBorder: "rgba(255,201,77,.28)",
        textColor: "#ffc94d",
        pulse: false,
      }
    case "offline":
      return {
        label: "ENGINE OFFLINE",
        dotColor: "#ff5a5a",
        pillBg: "rgba(255,90,90,.10)",
        pillBorder: "rgba(255,90,90,.30)",
        textColor: "#ff8f8a",
        pulse: false,
      }
    default: // "loading"
      return {
        label: "SYNCING",
        dotColor: "#8a8a8a",
        pillBg: "rgba(255,255,255,.04)",
        pillBorder: "rgba(255,255,255,.09)",
        textColor: "#8a8a8a",
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
  const { pathname } = useLocation()

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

  // Make the ⌘K hint honest: a global Cmd/Ctrl+K jumps to Ask — the same
  // navigation the command-field button performs on click. No palette overlay.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isCmdK(e)) {
        e.preventDefault()
        navigate("/ask")
      }
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [navigate])

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
          aria-label="Neurosurgery·Signal home"
        >
          <BrainMark />
          <div className="flex flex-col leading-none">
            <span className="font-display text-base font-semibold tracking-tight text-foreground">
              Neurosurgery<span style={{ color: "#666" }}>·</span>Signal
            </span>
            <span
              className="font-mono font-bold uppercase text-muted-foreground"
              style={{ fontSize: "9px", letterSpacing: "0.18em" }}
            >
              Telemetry Console
            </span>
          </div>
        </NavLink>

        {/* ── Nav buttons: Ask / Dossier / Cards (active = blue pill, cyan text) ── */}
        <ul className="flex shrink-0 items-center gap-1" role="list">
          {NAV_LINKS.map((l) => (
            <li key={l.to}>
              <NavLink
                to={l.to}
                className={({ isActive }) =>
                  cn(
                    "inline-block rounded-full border px-3.5 py-1.5 font-mono text-[11px] font-bold uppercase tracking-[0.14em] transition-colors duration-150",
                    isActive
                      ? "border-[rgba(107,147,255,.28)] bg-[rgba(107,147,255,.14)] text-[#34dfe6]"
                      : "border-transparent text-muted-foreground hover:text-foreground",
                  )
                }
              >
                {l.label}
              </NavLink>
            </li>
          ))}
        </ul>

        {/* ── Center: "Ask the corpus" command field with ⌘K hint — hidden on /ask (page owns the input) ── */}
        {shouldShowNavSearch(pathname) ? (
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
        ) : (
          <div className="mx-auto flex-1" aria-hidden />
        )}

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
