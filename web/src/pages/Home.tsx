import { Link } from "react-router-dom"
import HealthPanel from "@/components/HealthPanel"
import BlurText from "@/components/BlurText"
import { Card, Eyebrow } from "@/components/ui"

const SURFACES = [
  {
    to: "/ask",
    tag: "Ask",
    body: "Citation-grounded answers from your neurosurgery textbooks, augmented with contemporary PubMed literature.",
  },
  {
    to: "/build",
    tag: "Build",
    body: "A structured, corpus-grounded pre-operative dossier — anatomy at risk, operative plan, risk & rescue.",
  },
  {
    to: "/cards",
    tag: "Cards",
    body: "Hybrid search over your personal ABNS / SANS board-review deck — matched, not synthesized.",
  },
]

export default function Home() {
  return (
    <div className="flex flex-col gap-12">
      {/* Hero */}
      <section className="relative pt-8">
        {/* brutalist accent block behind the title */}
        <div
          aria-hidden
          className="pointer-events-none absolute -top-3 left-0 h-12 w-32 border-2 border-border bg-secondary"
        />
        <div className="reveal" style={{ animationDelay: "0ms" }}>
          <Eyebrow accent>Neurosurgery Signal · Local console</Eyebrow>
        </div>
        <div
          className="reveal mt-4 [&>.blur-text]:flex-nowrap"
          style={{ animationDelay: "90ms" }}
        >
          <BlurText
            text="Neuro·Caseboard"
            animateBy="letters"
            delay={55}
            className="font-display text-2xl font-extrabold leading-[1.05] tracking-tight text-foreground sm:text-5xl lg:text-6xl"
          />
        </div>
        <p
          className="reveal mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground"
          style={{ animationDelay: "200ms" }}
        >
          One local surface over your citation-grounded neurosurgery engine — ask, build a pre-op
          board, and search your card bank.{" "}
          <span className="text-muted-foreground">
            Decision-support only; verify against primary sources.
          </span>
        </p>
      </section>

      <div className="reveal" style={{ animationDelay: "320ms" }}>
        <HealthPanel />
      </div>

      <section className="reveal grid gap-4 sm:grid-cols-3" style={{ animationDelay: "440ms" }}>
        {SURFACES.map((s) => (
          <Link key={s.to} to={s.to} className="group">
            <Card hover className="h-full p-5">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs uppercase tracking-[0.2em] text-primary">
                  {s.tag}
                </span>
                <span className="font-mono text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary">
                  →
                </span>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{s.body}</p>
            </Card>
          </Link>
        ))}
      </section>
    </div>
  )
}
