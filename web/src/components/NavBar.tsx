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
    <header className="site-header sticky top-0 z-30">
      <nav className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3.5">
        <NavLink to="/" className="group flex items-center gap-2.5">
          <span
            className="grid h-7 w-7 place-items-center border-2 border-border bg-primary text-primary-foreground"
            aria-hidden
          >
            ◈
          </span>
          <span className="font-display text-lg font-bold tracking-tight text-foreground">
            Neuro<span className="text-primary-ink">·</span>Caseboard
          </span>
        </NavLink>
        <ul className="flex items-center gap-1.5">
          {LINKS.map((l) => (
            <li key={l.to}>
              <NavLink
                to={l.to}
                end={l.end}
                className={({ isActive }) =>
                  cn(
                    "border-2 px-3 py-1.5 font-mono text-[11px] font-bold uppercase tracking-[0.14em] transition-colors",
                    isActive
                      ? "border-border bg-primary text-primary-foreground"
                      : "border-transparent text-muted-foreground hover:border-border hover:bg-secondary hover:text-foreground",
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
