import { NavLink } from "react-router-dom"
import { cn } from "@/lib/utils"

const LINKS = [
  { to: "/", label: "Home", end: true },
  { to: "/ask", label: "Ask", end: false },
  { to: "/build", label: "Build", end: false },
  { to: "/cards", label: "Cards", end: false },
]

export default function NavBar() {
  return (
    <header className="sticky top-0 z-20 border-b border-navy-700/60 bg-navy-950/80 backdrop-blur">
      <nav className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
        <NavLink to="/" className="flex items-center gap-2">
          <span className="text-teal" aria-hidden>
            ◈
          </span>
          <span className="font-display text-lg font-bold tracking-tight text-ink">
            Neuro<span className="text-ink-dim">·</span>Caseboard
          </span>
        </NavLink>
        <ul className="flex items-center gap-1">
          {LINKS.map((l) => (
            <li key={l.to}>
              <NavLink
                to={l.to}
                end={l.end}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-3 py-1.5 font-mono text-xs uppercase tracking-wider transition-colors",
                    isActive
                      ? "bg-teal/10 text-teal"
                      : "text-ink-dim hover:bg-navy-800 hover:text-ink",
                  )
                }
              >
                {l.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  )
}
