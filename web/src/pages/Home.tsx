import { Link } from "react-router-dom"
import CircleOfWillis from "@/components/CircleOfWillis"

// ── ECG waveform point generator ──────────────────────────────────────────────
// Produces a `<polyline points>` string: `cycles` ECG cycles,
// each `cycleW` px wide, centred on the `mid` y value.
function ecgPoints(cycles: number, cycleW: number, mid: number): string {
  const pts: string[] = []
  for (let c = 0; c < cycles; c++) {
    const x = c * cycleW
    pts.push(`${x},${mid}`)
    pts.push(`${x + cycleW * 0.15},${mid}`)
    pts.push(`${x + cycleW * 0.17},${mid - 6}`)
    pts.push(`${x + cycleW * 0.20},${mid}`)
    pts.push(`${x + cycleW * 0.28},${mid}`)
    pts.push(`${x + cycleW * 0.30},${mid + 4}`)
    pts.push(`${x + cycleW * 0.33},${mid - 24}`)
    pts.push(`${x + cycleW * 0.36},${mid + 8}`)
    pts.push(`${x + cycleW * 0.39},${mid}`)
    pts.push(`${x + cycleW * 0.47},${mid - 1}`)
    pts.push(`${x + cycleW * 0.54},${mid - 10}`)
    pts.push(`${x + cycleW * 0.62},${mid}`)
    pts.push(`${x + cycleW * 1.0},${mid}`)
  }
  return pts.join(" ")
}

// 8 cycles × 150 px = 1200 px; two copies → 2400 px scroll loop
const ECG_PTS = ecgPoints(8, 150, 30)

// ── Pathway cards ─────────────────────────────────────────────────────────────
const PATHWAYS = [
  {
    to: "/ask",
    eyebrow: "ASK",
    title: "Ask the corpus",
    body: "Citation-grounded answers from your neurosurgery textbooks, augmented with contemporary PubMed literature.",
    linkLabel: "Open ask",
    accentColor: "#ff7363",
    borderColor: "rgba(216,65,58,.3)",
    hoverBorder: "rgba(216,65,58,.6)",
    bgColor: "rgba(216,65,58,.06)",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
  },
  {
    to: "/build",
    eyebrow: "DOSSIER",
    title: "Pre-op caseboard",
    body: "A structured, corpus-grounded pre-operative dossier — anatomy at risk, operative plan, risk and rescue.",
    linkLabel: "Open dossier",
    accentColor: "#6fc0b8",
    borderColor: "rgba(63,150,144,.3)",
    hoverBorder: "rgba(63,150,144,.6)",
    bgColor: "rgba(63,150,144,.06)",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
      </svg>
    ),
  },
  {
    to: "/cards",
    eyebrow: "CARDS",
    title: "Board-review deck",
    body: "Hybrid search over your personal ABNS / SANS board-review deck — matched, never synthesized.",
    linkLabel: "Open cards",
    accentColor: "#e0a86a",
    borderColor: "rgba(216,154,63,.3)",
    hoverBorder: "rgba(216,154,63,.6)",
    bgColor: "rgba(216,154,63,.06)",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="2" y="5" width="20" height="14" rx="2" />
        <line x1="2" y1="10" x2="22" y2="10" />
      </svg>
    ),
  },
] as const

// ── Evidence states ────────────────────────────────────────────────────────────
const EVIDENCE_STATES = [
  {
    status: "SUPPORTED",
    color: "#5fa86f",
    dot: "#74c084",
    bg: "rgba(95,168,111,.07)",
    borderLeft: "#5fa86f",
    desc: "Claims directly supported by corpus-grounded citations with traceable source spans.",
  },
  {
    status: "TO VERIFY",
    color: "#d89a3f",
    dot: "#ecae5e",
    bg: "rgba(216,154,63,.07)",
    borderLeft: "#d89a3f",
    desc: "Claims that lack complete corpus backing — plausible but require manual primary-source confirmation.",
  },
  {
    status: "QUARANTINED",
    color: "#c0564f",
    dot: "#cf6a62",
    bg: "rgba(192,86,79,.07)",
    borderLeft: "#c0564f",
    desc: "Claims that could not be grounded or were flagged for contradiction. Held back from the operative summary.",
  },
] as const

// ── Stats (illustrative marketing figures for the landing page) ───────────────
const STATS = [
  {
    value: "12",
    label: "Textbook volumes indexed",
    gradient: "linear-gradient(120deg,#d8413a,#ff7363)",
  },
  {
    value: "0",
    label: "Fabricated citations",
    gradient: "linear-gradient(120deg,#5fa86f,#74c084)",
  },
  {
    value: "4",
    label: "Operative pathways",
    gradient: "linear-gradient(120deg,#3f9690,#6fc0b8)",
  },
  {
    value: "100%",
    label: "Source-grounded answers",
    gradient: "linear-gradient(120deg,#d89a3f,#e8a24a 60%,#b3742a)",
  },
] as const

// ── Home ──────────────────────────────────────────────────────────────────────
export default function Home() {
  return (
    <div className="flex flex-col">

      {/* ── Hero ───────────────────────────────────────────────────────────── */}
      <section
        className="reveal grid items-center gap-10 py-12"
        style={{
          gridTemplateColumns: "1.04fr 0.96fr",
          minHeight: "80vh",
          animationDelay: "0ms",
        }}
      >
        {/* Left — copy */}
        <div className="flex flex-col gap-6">
          <p
            className="font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
            style={{ color: "#6fc0b8" }}
          >
            DECISION-SUPPORT FOR THE OPERATIVE FIELD
          </p>

          <h1
            className="leading-[1.05] tracking-tight"
            style={{ fontSize: "clamp(38px,5vw,62px)", fontWeight: 600, color: "#f1ece6" }}
          >
            Where millimeters decide{" "}
            <span
              style={{
                background: "linear-gradient(120deg,#d8413a,#e8a24a 60%,#b3742a)",
                WebkitBackgroundClip: "text",
                backgroundClip: "text",
                color: "transparent",
              }}
            >
              everything.
            </span>
          </h1>

          <p
            className="max-w-md text-base leading-relaxed"
            style={{ color: "#a79e98" }}
          >
            Citation-grounded neurosurgery decision-support. Every answer traces to a corpus
            source span — no hallucinated references, no fabricated risk numbers, no simulated
            clinical data.
          </p>

          <div className="flex flex-wrap items-center gap-3 pt-2">
            {/* Primary CTA */}
            <Link
              to="/ask"
              className="inline-flex items-center gap-2 font-sans font-semibold text-white no-underline transition-shadow duration-200"
              style={{
                background: "linear-gradient(135deg,#d8413a,#ff7363)",
                borderRadius: "var(--radius-md)",
                boxShadow: "0 6px 22px rgba(216,65,58,.32)",
                fontSize: "0.9rem",
                padding: "0.72rem 1.5rem",
              }}
            >
              Open the console
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <line x1="5" y1="12" x2="19" y2="12" />
                <polyline points="12 5 19 12 12 19" />
              </svg>
            </Link>

            {/* Ghost button — static, no navigation; real <button> for keyboard access */}
            <button
              type="button"
              className="inline-flex cursor-default items-center gap-2 font-sans font-medium"
              style={{
                background: "transparent",
                border: "1px solid rgba(255,255,255,.13)",
                borderRadius: "var(--radius-md)",
                color: "#a79e98",
                fontSize: "0.9rem",
                padding: "0.72rem 1.25rem",
              }}
              aria-label="How grounding works — coming soon"
              onClick={() => undefined}
            >
              How grounding works
            </button>
          </div>
        </div>

        {/* Right — Circle of Willis */}
        <CircleOfWillis style={{ maxWidth: 480, justifySelf: "end" }} />
      </section>

      {/* ── Standard / ECG band ────────────────────────────────────────────── */}
      <section
        className="relative overflow-hidden py-20"
        style={{
          // Full-bleed via the classic 100vw trick; the parent is max-w-5xl padded
          position: "relative",
          width: "100vw",
          left: "50%",
          transform: "translateX(-50%)",
        }}
      >
        {/* Horizontally-scrolling ECG line */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 flex items-center"
          style={{
            maskImage:
              "linear-gradient(90deg,transparent,rgba(0,0,0,.65) 14%,rgba(0,0,0,.65) 86%,transparent)",
            WebkitMaskImage:
              "linear-gradient(90deg,transparent,rgba(0,0,0,.65) 14%,rgba(0,0,0,.65) 86%,transparent)",
          }}
        >
          {/* Two copies → total 2400 px; scroll keyframe moves -50% = -1200 px → seamless */}
          <div
            style={{
              display: "flex",
              flexShrink: 0,
              animation: "scroll 9s linear infinite",
              willChange: "transform",
            }}
          >
            {([0, 1] as const).map((i) => (
              <svg
                key={i}
                viewBox="0 0 1200 60"
                width="1200"
                height="60"
                preserveAspectRatio="none"
                style={{ display: "block", flexShrink: 0 }}
              >
                <polyline
                  points={ECG_PTS}
                  fill="none"
                  stroke="rgba(95,168,111,.5)"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            ))}
          </div>
        </div>

        {/* Statement */}
        <div className="relative z-10 mx-auto px-6 text-center" style={{ maxWidth: 720 }}>
          <p
            className="font-sans leading-[1.55]"
            style={{ fontSize: "clamp(1.1rem,2.2vw,1.45rem)", color: "#bdb4ac" }}
          >
            In the operative field,{" "}
            <span style={{ color: "#ff7363", fontWeight: 600 }}>approximately right</span>
            {" "}is wrong. Neuro·Caseboard grounds every claim in a{" "}
            <span style={{ color: "#e0a86a", fontWeight: 500 }}>traceable corpus span</span>
            {" "}— because at millimeter scale, the{" "}
            <span style={{ color: "#f1ece6" }}>source matters.</span>
          </p>
        </div>
      </section>

      {/* ── Three pathways ─────────────────────────────────────────────────── */}
      <section className="reveal py-16" style={{ animationDelay: "80ms" }}>
        <p
          className="mb-8 font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
          style={{ color: "#6fc0b8" }}
        >
          THREE PATHWAYS
        </p>
        <div className="grid gap-5" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
          {PATHWAYS.map((p) => (
            <Link key={p.to} to={p.to} className="no-underline">
              <div
                className="flex h-full flex-col gap-4 p-6 transition-all duration-200 hover:-translate-y-1"
                style={{
                  background: p.bgColor,
                  border: `1px solid ${p.borderColor}`,
                  borderRadius: "var(--radius-lg)",
                }}
              >
                <span style={{ color: p.accentColor }}>{p.icon}</span>
                <div>
                  <p
                    className="font-mono text-[10px] uppercase tracking-[0.18em]"
                    style={{ color: p.accentColor, marginBottom: "0.25rem" }}
                  >
                    {p.eyebrow}
                  </p>
                  <p
                    className="font-sans font-semibold"
                    style={{ color: "#f1ece6", fontSize: "1rem" }}
                  >
                    {p.title}
                  </p>
                </div>
                <p
                  className="grow text-sm leading-relaxed"
                  style={{ color: "#a79e98" }}
                >
                  {p.body}
                </p>
                <p className="font-sans text-sm font-medium" style={{ color: p.accentColor }}>
                  {p.linkLabel} →
                </p>
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* ── Evidence states ────────────────────────────────────────────────── */}
      <section className="reveal py-8" style={{ animationDelay: "160ms" }}>
        <p
          className="mb-8 font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
          style={{ color: "#e0a86a" }}
        >
          EVIDENCE STATES
        </p>
        <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
          {EVIDENCE_STATES.map((es) => (
            <div
              key={es.status}
              className="flex flex-col gap-3 p-5"
              style={{
                background: es.bg,
                border: "1px solid rgba(255,255,255,.08)",
                borderLeft: `3px solid ${es.borderLeft}`,
                borderRadius: "var(--radius-lg)",
              }}
            >
              <div className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  style={{
                    display: "inline-block",
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: es.dot,
                    boxShadow: `0 0 7px ${es.dot}`,
                    animation: "pulse 2.4s ease-in-out infinite",
                    flexShrink: 0,
                  }}
                />
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                  style={{ color: es.color }}
                >
                  {es.status}
                </p>
              </div>
              <p className="text-sm leading-relaxed" style={{ color: "#a79e98" }}>
                {es.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Stats (illustrative landing figures, not live data) ─────────────── */}
      <section className="reveal py-8" style={{ animationDelay: "240ms" }}>
        <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
          {STATS.map((s) => (
            <div
              key={s.label}
              className="flex flex-col gap-2 p-5"
              style={{
                background:
                  "linear-gradient(160deg,rgba(255,255,255,.05),rgba(255,255,255,.012))",
                border: "1px solid rgba(255,255,255,.09)",
                borderRadius: "var(--radius-lg)",
                backdropFilter: "blur(14px)",
              }}
            >
              <span
                className="tnum font-display font-bold leading-none"
                style={{
                  fontSize: "clamp(2rem,4vw,2.6rem)",
                  background: s.gradient,
                  WebkitBackgroundClip: "text",
                  backgroundClip: "text",
                  color: "transparent",
                }}
              >
                {s.value}
              </span>
              <span
                className="font-mono text-[10px] uppercase tracking-[0.15em]"
                style={{ color: "#766a64" }}
              >
                {s.label}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* ── Final CTA ──────────────────────────────────────────────────────── */}
      <section className="reveal py-8" style={{ animationDelay: "320ms" }}>
        <div
          className="flex flex-col items-center gap-6 p-12 text-center"
          style={{
            background:
              "linear-gradient(135deg,rgba(216,65,58,.12),rgba(63,150,144,.08))",
            border: "1px solid rgba(216,65,58,.22)",
            borderRadius: "var(--radius-xl)",
          }}
        >
          <h2
            className="font-display font-semibold leading-tight tracking-tight"
            style={{ fontSize: "clamp(1.5rem,3vw,2rem)", color: "#f1ece6" }}
          >
            Bring the literature into the room.
          </h2>
          <p className="max-w-md text-sm leading-relaxed" style={{ color: "#a79e98" }}>
            Ground your pre-operative planning in a searchable, citation-verified neurosurgical
            corpus — evidence at your fingertips, honesty baked in.
          </p>
          <Link
            to="/ask"
            className="inline-flex items-center gap-2 font-sans font-semibold text-white no-underline transition-shadow duration-200"
            style={{
              background: "linear-gradient(135deg,#d8413a,#ff7363)",
              borderRadius: "var(--radius-md)",
              boxShadow: "0 6px 22px rgba(216,65,58,.32)",
              fontSize: "0.9rem",
              padding: "0.72rem 1.75rem",
            }}
          >
            Start asking
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="12 5 19 12 12 19" />
            </svg>
          </Link>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <footer className="py-10 text-center">
        <p
          className="font-mono text-[10px] uppercase tracking-[0.2em]"
          style={{ color: "#766a64" }}
        >
          NEURO·CASEBOARD · LOCAL ENGINE · DECISION-SUPPORT ONLY
        </p>
        <p className="mt-2 text-xs" style={{ color: "#5a504c" }}>
          Verify all claims against primary sources before clinical use. This tool does not
          provide medical advice.
        </p>
      </footer>
    </div>
  )
}
