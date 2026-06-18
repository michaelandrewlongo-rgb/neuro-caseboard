# GUI Council Scorecard — Neuro·Caseboard web console

Living measurement of interface design, accessibility, user-friendliness, and appearance.
Refreshed every cycle. Evidence: headless-Chromium screenshots + `@axe-core/playwright` audits in
`gui-council/` (regenerate: `NODE_PATH=web/node_modules LABEL=<name> node gui-council/capture.cjs`;
semantics/motion/keyboard: `node gui-council/verify.cjs`).

Stack under test: my worktree Vite on **:5174** → API on **:8001** (started from this worktree, so
`/api/health` is fully green incl. the integrated NCBI key).

Targets: **0 serious/critical axe**, **Lighthouse a11y ≥ 95**, WCAG 2.2 AA contrast on every pair,
keyboard-operable end-to-end with visible focus, `prefers-reduced-motion` honored, 0 console errors,
no overflow at 390w / 1280w.

---

## axe-core violations (failing-node count by impact)

| Surface (state)      | baseline serious | **now** | rules now |
|----------------------|:----------------:|:-------:|-----------|
| home 1280 / 390      | 6 / 6 | **0** | clean |
| ask 1280 / 390       | 2 / 2 | **0** | clean |
| build 1280 / 390     | 2 / 2 | **0** | clean |
| cards 1280 / 390     | 2 / 2 | **0** | clean |
| ask 1280 (loading)   | 6 | **0** | clean |
| build 1280 (loading) | 8 | **0** | clean |
| cards 1280 (loading) | 5 | **0** | clean |
| **TOTAL**            | **43** | **0** | — |

✅ Primary target met: **0 violations of any impact** across all 11 captures (cycle2).

## WCAG 2.2 AA contrast

All previously-failing pairs (every one was `#ff3333` text/fill at 3.63:1) now pass — see Cycle 1.
Two-token model: bright `--color-primary/#ff3333` fills carry **black** text (5.8:1); red/green/amber
**text** uses `--color-*-ink` darker variants (≥5:1 on white). Citation chips unchanged (already AA).

## Checklist metrics

| Metric | Baseline | Now | Notes |
|---|:---:|:---:|---|
| 0 serious/critical axe | ✗ (43) | ✅ 0 | all 11 captures clean |
| Keyboard operable end-to-end | ◐ | ✅ | skip-to-content link added; first Tab → skip link (verified) |
| Visible focus on every control | ◐ | ✅ | verified: buttons/links/skip-link get 3px red `:focus-visible` ring; `.field` inputs get red border+shadow |
| `prefers-reduced-motion` honored | ✗ | ✅ | BlurText renders static (verified 0 spans); `.animate-pulse` stopped; `.reveal` already honored |
| Live region for slow async results | ✗ | ✅ | loaders `role=status`+`aria-busy`+sr-only summary; per-page persistent `aria-live` announces completion |
| Status not by color alone | ✓ | ✓ | dot + text label; badges labelled |
| Page has `<h1>` | ✗ home | ✅ | BlurText gained `as` prop; Home title is a real `<h1>` (verified) |
| No console errors | ✓ | ✓ | clean on all surfaces/states |
| Responsive 390 / 1280 | ✓ | ✓ | no overflow/clipping; axe clean at 390 |
| Lighthouse accessibility | — | ✅ 100 | **100 on all 4 routes** (clean re-run; first batch flaky mid-HMR). best-practices N/A in dev (`valid-source-maps` only) |
| Token-system consistency | ◐ | ✅ | 1px `rounded-lg` → 2px square (SourcesList, CardItem img, Ask clarification); disabled button now legible muted (was opacity-40, 1.6:1) |

Legend: ✓/✅ pass · ◐ partial · ✗ fail · ⧖ pending

---

## Cycle history

| Cycle | Increment | serious axe (total) | Evidence |
|------:|-----------|:-------------------:|----------|
| 0 | baseline + unblock broken build | 43 | shots/axe `baseline/` |
| 1 | contrast fix (Path B: bright fills + black labels + `-ink` text) | 43 → **0 contrast** | shots/axe `cycle1/` |
| 2 | a11y completion: `<h1>`, skip link, reduced-motion, async live regions | → **0 total** | shots/axe `cycle2/`, `verify` |
| 3 | token-drift cleanup (1px→2px borders) + legible disabled button | 0 (held) | shots/axe `cycle3/` |

### Stop condition — status
✅ 0 serious/critical axe (0 of any impact) · ✅ Lighthouse a11y 100 (≥95) · ✅ WCAG AA contrast all pairs ·
✅ keyboard operable + skip link · ✅ reduced-motion honored · ✅ 0 console errors · ✅ responsive 390/1280.
Remaining nice-to-haves (not blockers): full manual SR sweep; ~500KB JS bundle code-split (perf, not a11y).
