import { Routes, Route } from "react-router-dom"
import NavBar from "@/components/NavBar"
import Home from "@/pages/Home"
import Ask from "@/pages/Ask"
import Build from "@/pages/Build"
import Cards from "@/pages/Cards"

export default function App() {
  return (
    <div className="min-h-screen text-foreground">
      <NavBar />
      <main className="mx-auto max-w-5xl px-6 py-10">
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
