import { Routes, Route } from "react-router-dom"
import NavBar from "@/components/NavBar"
import Home from "@/pages/Home"
import Ask from "@/pages/Ask"
import Build from "@/pages/Build"
import Cards from "@/pages/Cards"

export default function App() {
  return (
    <div className="min-h-screen text-foreground">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:border-2 focus:border-border focus:bg-secondary focus:px-4 focus:py-2 focus:font-mono focus:text-sm focus:font-bold focus:text-foreground"
      >
        Skip to content
      </a>
      <NavBar />
      <main id="main" tabIndex={-1} className="mx-auto max-w-5xl px-6 py-10 focus:outline-none">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/ask" element={<Ask />} />
          <Route path="/build" element={<Build />} />
          <Route path="/cards" element={<Cards />} />
        </Routes>
      </main>
    </div>
  )
}
