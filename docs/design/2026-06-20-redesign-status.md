# Neurosurgery·Signal redesign — status (2026-06-20)

The web front door + console were redesigned to the pure-black "Neurosurgery·Signal"
DTI-spectrum theme and merged to `master` in **PR #44** (`011a540`):

- **Landing** (`/`) — black/DTI hero with the whole-brain tractography canvas, default pathway.
- **Console** — Ask / Dossier (Build) / Cards retheme (palette + typography only; all real
  data wiring intact). Design reference: `docs/design/neuro-pages-latest/`.

## Where it stands

- **Desktop / laptop: looks good.** Reviewed at desktop widths against the design reference
  (header, telemetry grids, radar/gauge, claim cards, evidence states, deck identity) — matches.

## TODO — refine the interface on phone / small viewports

The redesign is **desktop-first** and needs a responsive pass before it reads well on a phone:

- The console content column is a fixed `max-w` with multi-column telemetry grids
  (`grid-template-columns` with `fr` tracks) that don't collapse gracefully on narrow screens.
- The `NavBar` packs logo + Ask/Dossier/Cards pills + the ⌘K command bar + engine pill + avatar
  on one row — too dense for a phone; needs a compact / stacked / drawer treatment.
- The landing hero scale, H1 sizing, and section padding are tuned for wide viewports.

Goal: a dedicated mobile pass (breakpoints, stacked telemetry, collapsible nav) so the phone
experience matches the quality of the laptop one.
