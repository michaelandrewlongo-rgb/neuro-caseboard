import HealthPanel from "@/components/HealthPanel"
import BlurText from "@/components/BlurText"

const SURFACES = [
  { to: "/ask", tag: "Ask", body: "Citation-grounded answers from your neurosurgery textbooks, augmented with contemporary PubMed literature." },
  { to: "/build", tag: "Build", body: "A structured, corpus-grounded pre-operative dossier — anatomy at risk, operative plan, risk & rescue." },
  { to: "/cards", tag: "Cards", body: "Hybrid search over your personal ABNS / SANS board-review deck — matched, not synthesized." },
]

export default function Home() {
  return (
    <div className="flex flex-col gap-10">
      <section className="pt-6">
        <p className="mb-3 font-mono text-xs uppercase tracking-[0.3em] text-teal">
          Neurosurgery Signal · Local console
        </p>
        <BlurText
          text="Neuro·Caseboard"
          animateBy="letters"
          delay={60}
          className="font-display text-5xl font-extrabold leading-[1.05] tracking-tight text-ink sm:text-6xl"
        />
        <p className="mt-4 max-w-2xl text-lg text-ink-dim">
          One local surface over your citation-grounded neurosurgery engine — ask, build a
          pre-op board, and search your card bank. Decision-support only; verify against
          primary sources.
        </p>
      </section>

      <HealthPanel />

      <section className="grid gap-4 sm:grid-cols-3">
        {SURFACES.map((s) => (
          <a
            key={s.to}
            href={s.to}
            className="group rounded-xl border border-navy-700/60 bg-navy-900/40 p-5 transition-colors hover:border-teal/50 hover:bg-navy-850/60"
          >
            <span className="font-mono text-xs uppercase tracking-widest text-teal">
              {s.tag}
            </span>
            <p className="mt-2 text-sm text-ink-dim">{s.body}</p>
          </a>
        ))}
      </section>
    </div>
  )
}
