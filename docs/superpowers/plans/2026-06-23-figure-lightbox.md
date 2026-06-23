# Plan — P2 #5: figures not enlargeable (click-to-zoom lightbox)

**Goal:** In the Ask view, `FigureGrid` renders each figure in a fixed 4:3 `object-contain` box with
**no click affordance** — there's no way to see a figure larger. Add click-to-enlarge: clicking a
figure that has a real image opens a lightbox showing it at full size with its caption; ESC / backdrop /
close button dismiss it.

**Laziest correct approach — native `<dialog>`, no library.** HTML's `<dialog>` + `showModal()` gives a
modal with backdrop, ESC-to-close, focus-trap, and `aria-modal` for free (ponytail ladder rung 3: native
platform feature over a custom overlay + framer-motion + focus-trap lib). One shared `<dialog>` lifted to
the grid (single DOM node + `selected: Figure | null` state) beats one dialog per card.

**Only real images enlarge.** Placeholder figures (`image_available` false or no `image_url`) have
nothing to zoom, so they get no click affordance. The enlargeable test is a small pure predicate —
extract it to a lib file (NOT the component) so it doesn't trip `react-refresh/only-export-components`
(the lint lesson from slice 4's review).

**"Crop to figure region" (backlog aside):** already done upstream — `image_url` points to the figure
asset extracted at ingest, so the lightbox shows the cropped figure at max size. No extra crop logic.

---

- [x] **Step 1 — Click-to-enlarge lightbox in FigureGrid (frontend only)**
  - `web/src/lib/figures.ts` (NEW, pure): `figureIsEnlargeable(fig: Pick<Figure, "image_url" |
    "image_available">): boolean` = `Boolean(fig.image_url) && fig.image_available`. Deterministic,
    unit-testable, no React import.
  - `web/src/components/ask/FigureGrid.tsx`:
    - Lift `selected: Figure | null` + a `dialogRef` to the `FigureGrid` component.
    - `FigureCard` takes an `onEnlarge?: (fig) => void`. When `showImg` (image loaded, not failed),
      wrap the `<img>` in a `<button type="button">` (keyboard-accessible: Enter/Space native) that
      calls `onEnlarge(fig)`; add a subtle `cursor-zoom-in` + a small "⤢"/"ENLARGE" hint on hover.
      Placeholder path unchanged (no affordance — `figureIsEnlargeable` false).
    - Render ONE `<dialog ref={dialogRef} onClose={() => setSelected(null)}>` at grid level: shows the
      selected figure `<img>` at `max-h-[85vh] max-w-[90vw] object-contain` + caption + a close button.
      Open via `dialogRef.current?.showModal()` in the enlarge handler; close via `.close()` (native ESC
      fires `onClose` → clears state). Backdrop click closes (onClick where `e.target === dialog`).
    - Enlarged `<img>` gets `alt={fig.caption || fig.location}`.
  - `web/src/lib/figures.test.ts` (NEW): assert `figureIsEnlargeable` true when image_url present +
    image_available; false when image_available false, image_url null, or both.
  - Keep the web suite green; `npm --prefix web run build` (tsc) + `npm --prefix web run lint` clean.
  - **Verify:** `npm --prefix web run test` (incl new spec) + `npm --prefix web run build` + `lint`.

**Non-regression:** figures with no usable image still render the dashed placeholder exactly as today
(no click handler, no dialog). Honesty invariant untouched — this is pure presentation, no data changes.
