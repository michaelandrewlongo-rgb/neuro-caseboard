import type { CSSProperties, ReactNode } from "react"
import { Link } from "react-router-dom"
import BrainTractography from "@/components/BrainTractography"

/**
 * Home — "Neurosurgery·Signal" landing page (the default pathway, `/`).
 *
 * Recreated from the design reference
 * `docs/design/neuro-pages-latest/Neuro Landing.dc.html`: a monochrome-black
 * front door with a DTI-spectrum accent set and a whole-brain tractography
 * canvas hero. Full-bleed with its own sticky header — it renders OUTSIDE the
 * console chrome (see App.tsx routing), so the global NavBar/`max-w` wrapper
 * does not apply here.
 *
 * Console entries map to real routes: ASK → /ask, DOSSIER → /build,
 * CARDS → /cards (the prototype linked all three to the console file).
 * In-page nav uses anchors (#pathways / #evidence / #corpus).
 */

const MONO = "'Geist Mono', ui-monospace, monospace"

// DTI-spectrum accents, reused across the page (match the canvas hero)
const C = {
  ink: "#ededed",
  blue: "#6b93ff",
  green: "#34e07f",
  cyan: "#34dfe6",
  magenta: "#ff66d8",
  amber: "#ffc94d",
  red: "#ff5a5a",
  mute: "#8a8a8a",
} as const

// ── Brain glyph (header + footer logo) ────────────────────────────────────────
function BrainGlyph({ stroke, size, midline = false }: { stroke: string; size: number; midline?: boolean }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      stroke={stroke}
      strokeWidth="6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M38,18 C20,20 14,40 22,52 C12,60 16,80 34,82 C44,90 60,88 64,78 C82,78 86,58 78,48 C86,38 80,18 60,18 C54,12 44,12 38,18 Z" />
      {midline && <path d="M50,16 L50,84" opacity="0.55" />}
    </svg>
  )
}

// arrow glyph used on CTAs / pathway links
function Arrow({ size = 15 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </svg>
  )
}

// ── "How we get our answers" — four-step plain-language flow ───────────────────
const STEPS = [
  {
    n: "1",
    border: "rgba(107,147,255,0.5)",
    color: C.blue,
    title: "You ask in plain words",
    body: "Type the question the way you'd ask a senior colleague. No codes, no special syntax — just the question.",
  },
  {
    n: "2",
    border: "rgba(52,224,127,0.5)",
    color: C.cyan,
    title: "It searches your own shelf",
    body: "It looks only inside the texts, atlases, and cards you've loaded — never the open internet, never its own memory.",
  },
  {
    n: "3",
    border: "rgba(255,201,77,0.5)",
    color: C.amber,
    title: "It pulls the exact pages",
    body: "It finds the specific passages and figures that actually address your question and lays them out side by side.",
  },
  {
    n: "4",
    border: "rgba(52,224,127,0.5)",
    color: C.green,
    title: "It answers with receipts",
    body: (
      <>
        Every sentence is built from those pages, each tagged with a <span style={{ color: C.blue }}>[n]</span> you can
        click back to the source. Anything it can't source, it leaves out.
      </>
    ),
  },
] as const

// ── "Three ways in" — pathway cards ───────────────────────────────────────────
const PATHWAYS = [
  {
    to: "/ask",
    eyebrow: "ASK",
    title: "Cited answers",
    body: (
      <>
        Ask in plain language. Get a grounded answer with inline <span style={{ color: C.blue }}>[n]</span> citations,
        attached figures, and a separate contemporary-literature lane.
      </>
    ),
    link: "Open Ask",
    icon: (
      <svg width="44" height="44" viewBox="0 0 46 46" fill="none" aria-hidden="true">
        <circle cx="23" cy="23" r="20" stroke="rgba(107,147,255,0.35)" strokeWidth="1.5" />
        <circle cx="23" cy="23" r="12" stroke="rgba(107,147,255,0.6)" strokeWidth="1.5" />
        <circle cx="23" cy="23" r="3.5" fill={C.blue} />
      </svg>
    ),
  },
  {
    to: "/build",
    eyebrow: "DOSSIER",
    title: "A pre-op briefing",
    body: "A structured dossier for the exact procedure — anatomy at risk, operative plan, risk & rescue — every claim audited and exportable to PDF.",
    link: "Open Dossier",
    icon: (
      <svg width="44" height="44" viewBox="0 0 46 46" fill="none" aria-hidden="true">
        <rect x="9" y="8" width="28" height="6" rx="3" fill="rgba(52,224,127,0.65)" />
        <rect x="9" y="20" width="22" height="5" rx="2.5" fill="rgba(52,224,127,0.4)" />
        <rect x="9" y="30" width="26" height="5" rx="2.5" fill="rgba(52,224,127,0.4)" />
      </svg>
    ),
  },
  {
    to: "/cards",
    eyebrow: "CARDS",
    title: "Your board deck",
    body: "Hybrid search over your personal ABNS / SANS deck. Matched cards and media — retrieved, never synthesized.",
    link: "Open Cards",
    icon: (
      <svg width="44" height="44" viewBox="0 0 46 46" fill="none" aria-hidden="true">
        <rect x="11" y="13" width="26" height="20" rx="4" fill="rgba(255,102,216,0.32)" transform="rotate(-7 24 23)" />
        <rect x="9" y="14" width="26" height="20" rx="4" fill="rgba(255,102,216,0.58)" />
      </svg>
    ),
  },
] as const

// ── Evidence states ───────────────────────────────────────────────────────────
const EVIDENCE = [
  {
    accent: C.green,
    bg: "rgba(52,224,127,0.04)",
    border: "rgba(52,224,127,0.18)",
    titleColor: "#eafff2",
    bodyColor: "rgba(52,224,127,0.62)",
    title: "Supported",
    body: "Two or more passages in your corpus say the same thing. Shown with every source and figure attached — quote it as it stands.",
  },
  {
    accent: C.amber,
    bg: "rgba(255,201,77,0.04)",
    border: "rgba(255,201,77,0.2)",
    titleColor: "#fff3df",
    bodyColor: "rgba(255,201,77,0.66)",
    title: "To verify",
    body: "Rests on a single passage, or on sources that disagree. Still shown — but flagged, so you corroborate against primary literature before you lean on it.",
  },
  {
    accent: C.red,
    bg: "rgba(255,90,90,0.04)",
    border: "rgba(255,90,90,0.2)",
    titleColor: "#ffe6e3",
    bodyColor: "rgba(255,90,90,0.64)",
    title: "Quarantined",
    body: "No passage in your corpus supports it. Withheld from the answer entirely — you'll see that a gap exists, rather than invented text papering over it.",
  },
] as const

// ── Corpus stats ──────────────────────────────────────────────────────────────
const STATS = [
  { value: "12", label: "Reference texts indexed", sub: "LanceDB · figures + passages" },
  { value: "0", label: "Fabricated citations", sub: "grounded or it doesn't ship" },
  { value: "4", label: "Independent evidence lanes", sub: "synthesis · corpus · cards · PubMed" },
  { value: "100%", label: "Local-first", sub: "runs on your machine · no cloud" },
] as const

// shared style fragments
const eyebrow: CSSProperties = { fontFamily: MONO, fontSize: "11px", letterSpacing: "0.2em", color: "#777" }
const sectionWrap: CSSProperties = { maxWidth: 1120, margin: "0 auto", padding: "96px 40px 30px" }

function Eyebrow({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <span style={{ ...eyebrow, ...style }}>{children}</span>
}

// ── Home ──────────────────────────────────────────────────────────────────────
export default function Home() {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#000",
        color: C.ink,
        fontFamily: "'Geist', system-ui, sans-serif",
        WebkitFontSmoothing: "antialiased",
        overflowX: "hidden",
      }}
    >
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded focus:bg-white focus:px-4 focus:py-2 focus:font-mono focus:text-sm focus:font-bold focus:text-black"
      >
        Skip to content
      </a>

      {/* ── NAV ─────────────────────────────────────────────────────────────── */}
      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 50,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "15px 40px",
          background: "rgba(0,0,0,0.55)",
          backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <div
            style={{
              position: "relative",
              width: 28,
              height: 28,
              display: "grid",
              placeItems: "center",
              borderRadius: 7,
              background: "#0a0a0a",
              border: "1px solid rgba(255,255,255,0.14)",
            }}
          >
            <BrainGlyph stroke={C.ink} size={17} midline />
          </div>
          <div style={{ lineHeight: 1 }}>
            <div style={{ fontSize: "14.5px", fontWeight: 600, letterSpacing: "-0.01em" }}>
              Neurosurgery<span style={{ color: "#555" }}>·</span>Signal
            </div>
            <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.2em", color: "#666", marginTop: 3 }}>
              CITATION-GROUNDED ENGINE
            </div>
          </div>
        </div>
        <nav style={{ display: "flex", alignItems: "center", gap: 28 }} aria-label="Primary">
          <a href="#pathways" className="nl-nav-link" style={{ fontSize: "13.5px" }}>
            Pathways
          </a>
          <a href="#evidence" className="nl-nav-link" style={{ fontSize: "13.5px" }}>
            Evidence
          </a>
          <a href="#corpus" className="nl-nav-link" style={{ fontSize: "13.5px" }}>
            Corpus
          </a>
          <Link
            to="/ask"
            className="nl-btn-solid"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 7,
              fontSize: "13.5px",
              fontWeight: 500,
              color: "#000",
              padding: "8px 16px",
              borderRadius: 8,
              background: C.ink,
            }}
          >
            Open console
          </Link>
        </nav>
      </header>

      <main id="main" tabIndex={-1} style={{ outline: "none" }}>
        {/* ── HERO ──────────────────────────────────────────────────────────── */}
        <section
          className="reveal"
          style={{
            position: "relative",
            maxWidth: 1000,
            margin: "0 auto",
            padding: "60px 40px 56px",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            textAlign: "center",
          }}
        >
          {/* whole-brain tractography hero mark */}
          <div style={{ position: "relative", width: "min(480px,86vw)", aspectRatio: "1 / 1", margin: "12px 0 6px" }}>
            <div
              aria-hidden
              style={{
                position: "absolute",
                inset: "16%",
                borderRadius: "50%",
                background: "radial-gradient(circle at 50% 52%, rgba(107,147,255,0.3), transparent 66%)",
                filter: "blur(30px)",
              }}
            />
            <div style={{ position: "relative", width: "100%", height: "100%", animation: "nl-float 10s ease-in-out infinite" }}>
              <BrainTractography />
            </div>
          </div>

          <h1
            style={{
              margin: "10px 0 0",
              fontSize: "clamp(40px,6vw,64px)",
              lineHeight: 1.0,
              fontWeight: 600,
              letterSpacing: "-0.04em",
              textWrap: "balance",
            }}
          >
            All of neurosurgery,
            <br />
            <span
              style={{
                background: "linear-gradient(110deg,#ededed,#9a9a9a)",
                WebkitBackgroundClip: "text",
                backgroundClip: "text",
                color: "transparent",
              }}
            >
              within reach.
            </span>
          </h1>

          <p style={{ margin: "22px 0 0", maxWidth: 580, fontSize: "16.5px", lineHeight: 1.65, color: C.mute }}>
            Everything you're expected to know in neurosurgery is scattered across your textbooks, the latest journals,
            and your own flashcards. Neurosurgery Signal pulls all three into one console — and answers only in
            citations, each tagged to exactly where it came from: a reference text, a PubMed paper, or a card in your
            deck. Nothing invented.
          </p>

          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 12, marginTop: 32 }}>
            <Link
              to="/ask"
              className="nl-btn-solid"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 9,
                fontSize: "14.5px",
                fontWeight: 500,
                color: "#000",
                padding: "13px 22px",
                borderRadius: 10,
                background: C.ink,
              }}
            >
              Open the console
              <Arrow />
            </Link>
            <a
              href="#evidence"
              className="nl-btn-ghost"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 9,
                fontSize: "14.5px",
                fontWeight: 500,
                color: C.ink,
                padding: "13px 22px",
                borderRadius: 10,
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.14)",
              }}
            >
              How grounding works
            </a>
          </div>

          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 22, marginTop: 34 }}>
            {[
              { dot: C.green, label: "Grounded to your corpus" },
              { dot: C.amber, label: "No fabricated citations" },
              { dot: C.mute, label: "Local-first" },
            ].map((chip) => (
              <div key={chip.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: chip.dot }} aria-hidden />
                <span style={{ fontFamily: MONO, fontSize: 11, color: "#777" }}>{chip.label}</span>
              </div>
            ))}
          </div>
        </section>

        {/* ── ESSENCE BAND (THE PROBLEM) ────────────────────────────────────── */}
        <section
          style={{
            position: "relative",
            margin: "20px 0 0",
            padding: "64px 40px",
            borderTop: "1px solid rgba(255,255,255,0.07)",
            borderBottom: "1px solid rgba(255,255,255,0.07)",
          }}
        >
          <div style={{ position: "relative", maxWidth: 880, margin: "0 auto", textAlign: "center" }}>
            <Eyebrow style={{ letterSpacing: "0.22em" }}>THE PROBLEM</Eyebrow>
            <p
              style={{
                margin: "18px 0 0",
                fontSize: "clamp(22px,3vw,30px)",
                lineHeight: 1.4,
                fontWeight: 500,
                letterSpacing: "-0.015em",
                textWrap: "balance",
                color: C.ink,
              }}
            >
              In the OR, <span style={{ color: C.red }}>approximately right is wrong.</span> But the knowledge that makes
              it right is the hardest thing to reach — locked inside expensive, convoluted{" "}
              <span style={{ color: C.blue }}>reference texts</span>, sealed in{" "}
              <span style={{ color: C.cyan }}>journals behind paywalls</span>, or never written down at all: passed
              bedside to bedside as the <span style={{ color: C.magenta }}>heuristics of whoever trained you</span>. And
              the field now moves faster than any one person can read — no two surgeons learn it alike, and none can hold
              the whole of it in their head. This engine gathers every source in one place and answers only in citations
              — <span style={{ color: C.mute }}>each line pinned to where it came from, so you can learn it your own way.</span>
            </p>
          </div>
        </section>

        {/* ── HOW IT WORKS + THREE WAYS IN ──────────────────────────────────── */}
        <section id="pathways" style={sectionWrap}>
          <div style={{ maxWidth: 680 }}>
            <Eyebrow>HOW WE GET OUR ANSWERS</Eyebrow>
            <h2 style={{ margin: "14px 0 0", fontSize: "clamp(30px,4vw,38px)", fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1.08 }}>
              No guessing. Your own library, read back to you.
            </h2>
            <p style={{ margin: "18px 0 0", fontSize: "15.5px", lineHeight: 1.7, color: "#9a9a9a" }}>
              Most tools you've heard of make up fluent-sounding text from memory. This one does the opposite: it can
              only repeat what's already written in the neurosurgery books and cards{" "}
              <em style={{ color: C.magenta, fontStyle: "normal" }}>you</em> loaded into it. Four steps, every time.
            </p>
          </div>

          {/* four-step flow */}
          <div style={{ position: "relative", marginTop: 44, display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 18 }}>
            <div
              aria-hidden
              style={{
                position: "absolute",
                top: 21,
                left: "8%",
                right: "8%",
                height: 1,
                background:
                  "linear-gradient(90deg,transparent,rgba(255,255,255,0.14) 12%,rgba(255,255,255,0.14) 88%,transparent)",
                pointerEvents: "none",
              }}
            />
            {STEPS.map((s) => (
              <div key={s.n} style={{ position: "relative", padding: "0 4px" }}>
                <div
                  style={{
                    width: 42,
                    height: 42,
                    borderRadius: "50%",
                    display: "grid",
                    placeItems: "center",
                    background: "#0a0a0a",
                    border: `1px solid ${s.border}`,
                    fontFamily: MONO,
                    fontSize: 15,
                    color: s.color,
                    boxShadow: "0 0 0 5px #000",
                  }}
                >
                  {s.n}
                </div>
                <h3 style={{ margin: "18px 0 0", fontSize: 17, fontWeight: 600, letterSpacing: "-0.01em" }}>{s.title}</h3>
                <p style={{ margin: "9px 0 0", fontSize: "13.5px", lineHeight: 1.62, color: C.mute }}>{s.body}</p>
              </div>
            ))}
          </div>

          {/* three ways in */}
          <div
            style={{
              marginTop: 72,
              display: "flex",
              alignItems: "flex-end",
              justifyContent: "space-between",
              gap: 20,
              marginBottom: 40,
              flexWrap: "wrap",
            }}
          >
            <div>
              <Eyebrow>THREE WAYS IN</Eyebrow>
              <h2 style={{ margin: "14px 0 0", fontSize: "clamp(28px,3.6vw,34px)", fontWeight: 600, letterSpacing: "-0.03em" }}>
                Same engine, three front doors.
              </h2>
            </div>
            <p style={{ maxWidth: 340, fontSize: 14, lineHeight: 1.6, color: C.mute }}>
              From a bedside question to a full pre-op briefing to your board-review deck — each surfaces the same
              grounded evidence.
            </p>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 16 }}>
            {PATHWAYS.map((p) => (
              <Link
                key={p.to}
                to={p.to}
                className="nl-card"
                style={{
                  display: "block",
                  padding: "28px 26px",
                  borderRadius: 14,
                  background: "#0a0a0a",
                  border: "1px solid rgba(255,255,255,0.1)",
                  color: "inherit",
                }}
              >
                {p.icon}
                <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.16em", color: "#666", marginTop: 22 }}>
                  {p.eyebrow}
                </div>
                <h3 style={{ margin: "7px 0 0", fontSize: 21, fontWeight: 600, letterSpacing: "-0.01em" }}>{p.title}</h3>
                <p style={{ margin: "11px 0 0", fontSize: "13.5px", lineHeight: 1.6, color: C.mute }}>{p.body}</p>
                <div style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 18, fontSize: 13, fontWeight: 500, color: C.ink }}>
                  {p.link} <Arrow size={14} />
                </div>
              </Link>
            ))}
          </div>
        </section>

        {/* ── EVIDENCE STATES ───────────────────────────────────────────────── */}
        <section id="evidence" style={sectionWrap}>
          <div style={{ display: "grid", gridTemplateColumns: "0.85fr 1.15fr", gap: 48, alignItems: "center" }}>
            <div>
              <Eyebrow>EVIDENCE STATES</Eyebrow>
              <h2 style={{ margin: "14px 0 0", fontSize: "clamp(30px,4vw,38px)", fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1.1 }}>
                Honest about what it knows.
              </h2>
              <p style={{ margin: "18px 0 0", fontSize: 15, lineHeight: 1.7, color: C.mute }}>
                Every line the engine produces is labelled with its grounding. If a lane is unavailable, it says so — it
                will not fabricate a dossier, a citation, or a card to fill the gap.
              </p>
              <div
                style={{
                  marginTop: 26,
                  padding: "16px 18px",
                  borderRadius: 12,
                  background: "rgba(255,201,77,0.04)",
                  border: "1px solid rgba(255,201,77,0.16)",
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={C.amber} strokeWidth="2" style={{ flex: "none" }} aria-hidden="true">
                  <path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3Z" />
                  <path d="M12 9v4" />
                  <path d="M12 17h.01" />
                </svg>
                <span style={{ fontSize: "12.5px", color: "rgba(255,201,77,0.66)", lineHeight: 1.5 }}>
                  Decision-support only. Verify against primary sources before operative use.
                </span>
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {EVIDENCE.map((e) => (
                <div
                  key={e.title}
                  style={{
                    position: "relative",
                    padding: "22px 24px",
                    borderRadius: 14,
                    background: e.bg,
                    border: `1px solid ${e.border}`,
                  }}
                >
                  <span
                    aria-hidden
                    style={{
                      position: "absolute",
                      left: 0,
                      top: 18,
                      bottom: 18,
                      width: 3,
                      borderRadius: 3,
                      background: e.accent,
                      boxShadow: `0 0 10px ${e.accent}`,
                    }}
                  />
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span
                      aria-hidden
                      style={{ width: 9, height: 9, borderRadius: "50%", background: e.accent, boxShadow: `0 0 9px ${e.accent}` }}
                    />
                    <span style={{ fontSize: 17, fontWeight: 600, color: e.titleColor }}>{e.title}</span>
                  </div>
                  <p style={{ margin: "9px 0 0", fontSize: "13.5px", lineHeight: 1.6, color: e.bodyColor }}>{e.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── CORPUS / STATS ────────────────────────────────────────────────── */}
        <section id="corpus" style={{ maxWidth: 1120, margin: "0 auto", padding: "88px 40px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16 }}>
            {STATS.map((s) => (
              <div
                key={s.label}
                style={{ padding: "26px 24px", borderRadius: 14, background: "#0a0a0a", border: "1px solid rgba(255,255,255,0.1)" }}
              >
                <div className="tnum" style={{ fontSize: 40, fontWeight: 600, letterSpacing: "-0.03em", color: "#fafafa" }}>
                  {s.value}
                </div>
                <div style={{ fontSize: "13.5px", color: C.ink, marginTop: 8, fontWeight: 500 }}>{s.label}</div>
                <div style={{ fontFamily: MONO, fontSize: 10, color: "#666", marginTop: 4 }}>{s.sub}</div>
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* ── FOOTER ──────────────────────────────────────────────────────────── */}
      <footer
        style={{
          borderTop: "1px solid rgba(255,255,255,0.07)",
          padding: "34px 40px",
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 18,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <div
            style={{
              width: 24,
              height: 24,
              display: "grid",
              placeItems: "center",
              borderRadius: 6,
              background: "#0a0a0a",
              border: "1px solid rgba(255,255,255,0.14)",
            }}
          >
            <BrainGlyph stroke={C.blue} size={14} />
          </div>
          <span style={{ fontSize: 13, color: C.mute }}>
            Neurosurgery Signal — a local console over your grounded neurosurgery engine.
          </span>
        </div>
        <div style={{ display: "flex", gap: 24, fontFamily: MONO, fontSize: 11, color: "#666" }}>
          <span>v3 · LOCAL</span>
          <span>ENGINE · VERTEX</span>
          <span>NO AUTH · LOCALHOST</span>
        </div>
      </footer>
    </div>
  )
}
