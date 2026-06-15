# Neuro·Caseboard — Design Inspiration Scan & Action Report
**Date:** 2026-06-15 · **For:** the "Executive Navy" Streamlit system (`app/signal_theme.py`)
**Author:** product-design inspiration pass (research-grounded)

---

## Executive summary

The Executive Navy system is already in the right neighborhood: navy rail + bright report plane, a disciplined three-font split (Archivo / Source Serif 4 / IBM Plex Mono), single deep-teal accent, and an evidence-marker vocabulary. The highest-leverage gap is not the *look* but the *interaction depth around citations and evidence* — the exact thing the best clinical answer engines (OpenEvidence, Glass Health) and consumer answer engines (Perplexity) obsess over. Today our `[1]`/`[L1]` chips are inert `<span>`s; the single biggest upgrade is making them anchor-links that scroll to and highlight their source row, which is pure CSS/HTML and fully Streamlit-feasible. The second cluster of wins is a "craft pass" that the Vercel/Linear/Rauno-Freiberg school treats as table stakes: tabular numerals on every metric and citation, `:focus-visible` rings via `box-shadow` (not `outline`), `@media (hover:hover)` guards so touch doesn't get sticky hovers, and a single shared easing token. The third is borrowing Consensus's "evidence meter" idea as a compact stacked proportion bar so the supported/verify/quarantined split is legible at a glance, not just as three separate stat cards. On motion, Emil Kowalski's and Rauno's rules converge: keep everything ≤200ms, animate only `transform`/`opacity`, ease-out for enter, and add a `scale(0.97)` active-press — but note Streamlit re-runs replay entrance animations, so reserve motion for hover/active/focus (input-driven), not page-load. Color-wise we should keep the identity and only tighten contrast and elevation, following Stripe's perceptual-lightness discipline. Net: refine, don't replace — five concrete, low-risk changes move us from "nicely themed" to "crafted."

---

## References

### 1. Perplexity — citation-forward answer surface
- URLs: https://www.shapeof.ai/patterns/citations · https://www.aiuxplayground.com/gallery/perplexity-citations/ (case study)
- **The one brilliant thing:** a *multi-layered* citation system — inline numbered chips that carry lightweight metadata (favicon/title), a hover preview, and an expandable source list — so the prose stays clean while every claim is one gesture from its provenance. Quick-verify and full-inspect are different affordances on the same citation.
- **Apply to us:** our `.cc` chips already exist but are dead ends. Make them `<a href="#src-1">` that scroll to the matching `sources_panel`/`literature_panel` row, and give that row an `id` + a `:target` highlight so the destination flashes. That gives the "quick-verify" layer with zero JS. The "hover preview card" is the aspirational tier (needs JS to position a floating card from Streamlit-rendered markdown) — skip for now.

### 2. OpenEvidence — clinical answer engine, two-depth reads
- URLs: https://www.openevidence.com/ · https://research.contrary.com/company/openevidence
- **The one brilliant thing:** two deliberately different response depths — a fast "Consult" with citations inline after the text, and a long "Deep Consult" report with many references — plus references hyperlinked straight to abstracts. The depth is a first-class, named choice, not a hidden toggle.
- **Apply to us:** we already have Ask (fast) vs Build board (dossier). Borrow the *naming-as-affordance* idea: label the Ask answer's citation density and let "Build board" read as the Deep Consult equivalent. Concretely, the Sources panel should always hyperlink out (textbook page anchor or DOI) exactly as OpenEvidence links references to abstracts — our `literature_panel` already does DOI links; make `sources_panel` rows visually identical so the two evidence lanes feel like one system.

### 3. Glass Health — three-tier differential, evidence keyed by index
- URLs: https://glass.health/api-documentation · https://glass.health/resources/ai-diagnosis
- **The one brilliant thing:** DDx output is structured into three *tiers that mirror clinician cognition*, and their API explicitly documents the UI patterns evidence maps to: "inline citation markers preserved if you want evidence to stay attached to the prose… references can power a reference rail, expandable evidence section, or citation popovers, keyed by index."
- **Apply to us:** that "keyed by index" model is exactly our `[n]` ↔ source-row relationship — formalize it with `id="src-{n}"` anchors (see ref 1). The three-tier cognitive structuring is a content pattern for Build board: group dossier claims into tiers (e.g., Established / Supportive / To-verify) rather than a flat list, reusing the existing supported/verify/quarantined tones as the tier colors.

### 4. Consensus — the "Consensus Meter"
- URLs: https://paperguide.ai/blog/elicit-vs-consensus/ · https://consensus.app/
- **The one brilliant thing:** reduces 20 papers to a single yes/no/possibly bar readable "in under 10 seconds." A proportion visualization is doing the synthesis the user would otherwise do manually.
- **Apply to us:** add an **evidence-mix bar** — a single thin stacked horizontal bar showing the proportion of supported (`#0f766e`) / to-verify (`#a9781b`) / quarantined (`#b4493b`) claims in a board. It complements (doesn't replace) the three `.sig-metric` cards and is a pure flexbox HTML fragment. This is the single most "expensive-looking" cheap addition available to us.

### 5. Elicit — structured extraction as the interface
- URLs: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10089336/ · https://elicit.com/
- **The one brilliant thing:** results are a *table* (one row per paper, columns of extracted fields) with a continuously-updated summary in the left rail, plus journal-quartile (Q1–Q4) filtering. The table-as-evidence makes density a feature.
- **Apply to us:** our Literature lane could render as a denser, quieter table (title / journal·year / relevance) with mono micro-labels for the metadata columns, rather than prose rows. Quartile/recency chips map cleanly onto our mono `.sig-xref` pill style.

### 6. Linear — calm surface stack + rationed accent + LCH contrast
- URLs: https://linear.app/now/how-we-redesigned-the-linear-ui · https://blog.logrocket.com/ux-design/linear-design/
- **The one brilliant thing:** the whole UI lives in a *narrow elevation band* (background → foreground → panel → dialog → modal), the accent is rationed to primary actions only, and contrast is generated in a perceptually-uniform space (LCH) with a single "contrast" knob, after which they deliberately *darkened* light-mode text/icons for legibility.
- **Apply to us:** we already ration teal well. Two takeaways: (a) introduce a real elevation *stack* — today we jump page `#f6f7f9` → surface `#fff` with nothing between; add a `--surface-2` (~`#fbfcfd`) for nested/raised regions so depth reads as a ramp not a binary; (b) follow their "darken the text" move — our muted `#586676` on white is fine, but the secondary `#8a96a2` (`--faint`) is borderline for small text; reserve it for non-essential labels only.

### 7. Stripe — perceptual-lightness color discipline + tabular figures
- URLs: https://stripe.com/blog/accessible-color-systems (fetched) · https://uwux.medium.com/behind-the-gradient-design-at-stripe-476dcf61a51a
- **The one brilliant thing:** Stripe builds contrast in **CIELAB** because "at the same mathematical lightness, yellow appears lighter than blue," guarantees pairs are "at least five levels apart" for small text (4.5:1) / "four levels" for icons & large text (3:1), and uses **tabular figures wherever numerics matter**, with highly-contrasted primary text (`#0A2540`) that deliberately avoids pure black.
- **Apply to us:** our ink `#16202c` already avoids pure black — good. The actionable steal is **tabular figures** on every number (`.sig-metric .v`, `.cc`, `.sig-row .n`) so citation indices and metrics don't shimmy. And sanity-check our amber `#a9781b` and red `#b4493b` evidence markers for the "is it really 4.5:1 on white?" question (amber on white is the risk; darken to ~`#946a14` if used as small text rather than a swatch).

### 8. Emil Kowalski — practical animation values
- URL: https://emilkowal.ski/ui/7-practical-animation-tips (fetched)
- **The one brilliant thing:** specific, defensible numbers — UI motion <300ms (dropdowns feel better at ~180ms than 400ms), tooltips at 125ms, **ease-out for enter/exit and never ease-in**, built-in CSS easings "usually not strong enough" (use custom cubic-beziers), `scale(0.97)` on `:active` for press feedback, and never scale from `scale(0)` — start ~`0.9+`.
- **Apply to us:** our buttons use `transition: all .16s ease` + a `translateY(-1px)` hover. Upgrade to a shared easing token, drop `all` (animate specific props), add the `:active { transform: scale(.97) }` press. A "professional dashboard should be crisp and fast" — his words match our brief exactly.

### 9. Rauno Freiberg — Web Interface Guidelines (the craft checklist)
- URLs: https://interfaces.rauno.me/ · https://github.com/raunofreiberg/interfaces (fetched)
- **The one brilliant thing:** a dense list of the invisible details — `box-shadow` focus rings (because `outline` ignores `border-radius`), `@media (hover:hover)` so touch doesn't stick, `font-variant-numeric: tabular-nums`, 16px minimum input font (prevents iOS zoom), `-webkit-font-smoothing: antialiased` + `text-rendering: optimizeLegibility`, custom `::selection`, keep font-weight constant on hover to avoid layout shift, motion ≤200ms.
- **Apply to us:** this is a free "craft pass." We do focus rings right on inputs already; extend the same `box-shadow` ring to buttons/expanders/radios via `:focus-visible`, add `@media (hover:hover)` guards around every hover rule, add `::selection`, and confirm our input font is ≥16px (currently `.98rem` ≈ 15.7px — bump to 1rem).

### 10. Vercel / Geist — shadow-as-border + layered elevation
- URLs: https://vercel.com/geist/materials · https://www.shadcn.io/design/vercel
- **The one brilliant thing:** "shadow-as-border" (`box-shadow: 0 0 0 1px …`) plus multi-layer shadow stacks that bundle a hairline ring + elevation + ambient in one declaration, and **named elevation roles** (base/raised/tooltip/menu/modal) rather than ad-hoc shadows.
- **Apply to us:** our `--shadow` is already a sensible 2-layer recipe. Add the inset-hairline trick to cards (`0 0 0 1px rgba(16,32,48,.04)` as the first layer) so surfaces read crisp on the cool page even where a 1px border would feel heavy, and formalize 2–3 named shadow tokens (`--shadow-sm` / `--shadow` / `--shadow-pop`) used consistently.

### 11. NYT / The Pudding — editorial serif+sans pairing & annotation hierarchy
- URLs: https://en.wikipedia.org/wiki/The_Pudding · https://www.itsnicethat.com/features/gail-bichler-the-new-york-times-magazine-redesign-publication-spotlight-080426
- **The one brilliant thing:** a characterful serif for headlines/reading paired with a clean sans for labels/annotations, with a strict hierarchy of title → standfirst → annotation so text never competes with data. "Fewer words" — the visual essay leans on hierarchy, not volume.
- **Apply to us:** validates our Archivo-headline / Source-Serif-reading / mono-label split. The refinement is *optical sizing*: Source Serif 4 is a variable `opsz` font (we already import the axis) — add `font-optical-sizing: auto` so the standfirst/answer column uses display-optimized shapes at large sizes and text-optimized at body, which is the NYT-grade detail most people miss.

### 12. UpToDate / DynaMed — GRADE strength display
- URLs: https://www.wolterskluwer.com/en/solutions/uptodate/policies-legal/grading-guide · https://about.ebsco.com/clinical-decisions/dynamed-solutions/about/evidence-based-process/editorial-process
- **The one brilliant thing:** a *legible two-axis* grade — strength (Strong/Grade 1 vs Weak/Grade 2) × quality (A/B/C) — rendered as a compact, consistent badge so clinicians trust the calibration. DynaMed's concise bulleted, clear-hierarchy presentation outperforms prose for scanning.
- **Apply to us:** our single supported/verify/quarantined axis is good but flat. Consider a tiny two-part mono badge (e.g., `SRC · A` / `LIT · B`) reusing our citation-chip style, so an evidence marker can also carry a coarse quality grade without new color. Strictly additive; keep it optional.

---

## Technique catalog

1. **Anchor-link citation chips with `:target` flash** `[Streamlit-feasible]` — turn `.cc` spans into `<a href="#src-n">`; give source rows `id` + a `:target` highlight. Quick-verify provenance, zero JS.
2. **Tabular numerals everywhere numeric** `[Streamlit-feasible]` — `font-variant-numeric: tabular-nums` on `.sig-metric .v`, `.cc`, `.sig-row .n`. Stops index/metric jitter (Stripe, Rauno).
3. **`:focus-visible` rings via box-shadow, not outline** `[Streamlit-feasible]` — `box-shadow: 0 0 0 3px rgba(14,116,144,.30)`; respects `border-radius` (Rauno, Geist). Extend the input pattern to buttons/expanders/radios.
4. **`@media (hover:hover)` guards on all hover rules** `[Streamlit-feasible]` — prevents sticky hover states on touch after tap (Rauno).
5. **Shared motion easing token + active press** `[Streamlit-feasible]` — `--ease:cubic-bezier(.32,.72,0,1)`; transitions ≤180ms on specific props; `:active{transform:scale(.97)}` (Emil Kowalski). Note: Streamlit re-runs replay *entrance* animations, so confine motion to hover/active/focus, never `@keyframes` on load.
6. **Evidence-mix proportion bar** `[Streamlit-feasible]` — a thin stacked flex bar (supported/verify/quarantined widths) à la Consensus Meter; one HTML fragment.
7. **Elevation ramp: add `--surface-2` + named shadow tokens** `[Streamlit-feasible]` — `#fbfcfd` between page and surface; inset-hairline shadow layer (Linear, Geist).
8. **`::selection` brand styling** `[Streamlit-feasible]` — `::selection{background:rgba(14,116,144,.16);color:var(--ink)}` (Rauno).
9. **Optical sizing on the serif column** `[Streamlit-feasible]` — `font-optical-sizing:auto` on Source Serif 4 reading text (NYT-grade detail).
10. **Input font ≥16px** `[Streamlit-feasible]` — bump `.stTextInput input` to `1rem` to kill iOS focus-zoom (Rauno).
11. **Hover preview cards on citations** `[aspirational]` — floating source card on chip hover (Perplexity/Granola). Needs JS positioning over Streamlit markdown; not worth the fragility now.
12. **Skeleton shimmer loading state** `[aspirational]` — looks great but Streamlit's script re-run replays the keyframe on every interaction; a static "Retrieving evidence…" mono line with a single non-looping pulse is the safer call.

---

## Integrate-now shortlist (ranked, with exact values for `app/signal_theme.py`)

### 1. Clickable citation chips → scroll-to + flash the source row  *(citation UX — highest leverage)*
Make `citation_chips()` emit anchors, give panel rows ids, and add a `:target` rule.

```python
# citation_chips(): link [n] -> #src-n, [Ln] -> #lit-Ln
def citation_chips(md: str) -> str:
    def _sub(m):
        tok = m.group(1)
        anchor = f"lit-{tok}" if tok.startswith("L") else f"src-{tok}"
        return f'<a class="cc" href="#{anchor}">{tok}</a>'
    return re.sub(r"\[(L?\d{1,3})\](?!\()", _sub, md or "")
```
```css
a.cc{ text-decoration:none; cursor:pointer; transition:background .14s var(--ease), border-color .14s var(--ease); }
a.cc:hover{ background:rgba(14,116,144,.16); border-color:var(--accent); }
.sig-row{ scroll-margin-top:90px; }                 /* clears the sticky header on jump */
.sig-row:target{ animation:cc-flash 1.2s ease-out; } /* runs once on navigation, not on rerun */
@keyframes cc-flash{ 0%{ background:rgba(14,116,144,.14); } 100%{ background:transparent; } }
```
And in `sources_panel` / `literature_panel`, add the id to each row:
`<div class="sig-row" id="src-{n}">…</div>` and `id="lit-L{n}">…`.
*Why first:* it's the defining behavior of every great answer engine, it's pure CSS/HTML, and it makes our existing chips earn their keep. `:target` fires on click-navigation, not on Streamlit's rerun, so it won't nag.

### 2. Motion & focus craft pass  *(feel — cheap, system-wide)*
Add one easing token and reform the button/focus rules.

```css
:root{ --ease:cubic-bezier(.32,.72,0,1); }
/* buttons: specific props, faster, with press feedback */
.stButton>button, .stDownloadButton>button,
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-secondary"]{
  transition:background .16s var(--ease), border-color .16s var(--ease),
             box-shadow .16s var(--ease), transform .12s var(--ease);
}
@media (hover:hover){
  .stButton>button:hover, [data-testid="stBaseButton-primary"]:hover,
  .stDownloadButton>button:hover{ transform:translateY(-1px); }
}
.stButton>button:active, [data-testid="stBaseButton-primary"]:active{ transform:scale(.97); }
/* focus-visible rings that respect radius, reuse the input recipe everywhere */
.stButton>button:focus-visible, [data-testid="stBaseButton-secondary"]:focus-visible,
[data-testid="stExpander"] summary:focus-visible,
section[data-testid="stSidebar"] div[role="radiogroup"] label:focus-within{
  outline:none; box-shadow:0 0 0 3px rgba(14,116,144,.30);
}
```
*Values per Emil Kowalski (≤180ms, ease-out, `scale(.97)` active) and Rauno (box-shadow focus, `hover:hover`).* Wrap *all* existing hover declarations (sidebar labels, chips, expander summary) in `@media (hover:hover)`.

### 3. Numeric & typographic precision pass  *(legibility — trivial, high polish)*
```css
.sig-metric .v, .cc, a.cc, .sig-row .n, .sig-row .ln{ font-variant-numeric:tabular-nums; }
.stMarkdown p, .stMarkdown li, .sig-subtitle{ font-optical-sizing:auto; }  /* Source Serif 4 opsz */
::selection{ background:rgba(14,116,144,.16); color:var(--ink); }
.stTextInput input{ font-size:1rem; }   /* was .98rem (~15.7px) -> 16px, kills iOS zoom */
html,body,.stApp{ text-rendering:optimizeLegibility; }  /* pairs with existing antialiased */
```
*Stripe (tabular figures), Rauno (selection, 16px input, optimizeLegibility), NYT (optical sizing).*

### 4. Evidence-mix proportion bar  *(evidence display — the "expensive-looking" cheap win)*
A new helper next to `metrics()`/`legend()`:
```python
def evidence_bar(supported: int, verify: int, quarantined: int) -> None:
    total = max(supported + verify + quarantined, 1)
    seg = lambda n, var: (f'<span style="width:{n/total*100:.1f}%;background:{var}"></span>' if n else "")
    bar = seg(supported,"var(--supported)") + seg(verify,"var(--verify)") + seg(quarantined,"var(--quar)")
    _md(f'<div class="sig-evbar">{bar}</div>')
```
```css
.sig-evbar{ display:flex; height:8px; border-radius:999px; overflow:hidden;
  background:var(--line-soft); box-shadow:inset 0 0 0 1px rgba(16,32,48,.05); margin:.2rem 0 .9rem; }
.sig-evbar > span{ display:block; height:100%; }
.sig-evbar > span + span{ box-shadow:inset 1px 0 0 rgba(255,255,255,.65); } /* hairline seam */
```
*Consensus Meter, condensed. Place it directly above the existing three `.sig-metric` cards so the bar is the glance and the cards are the detail.*

### 5. Elevation ramp + inset-hairline shadows  *(depth — quiet refinement)*
```css
:root{
  --surface-2:#fbfcfd;                       /* nested/raised tier between page and surface */
  --shadow-sm:0 0 0 1px rgba(16,32,48,.04), 0 1px 2px rgba(16,32,48,.05);
  --shadow:0 0 0 1px rgba(16,32,48,.04), 0 1px 2px rgba(16,32,48,.05), 0 12px 26px rgba(16,32,48,.06);
}
.sig-panel, .sig-metric{ background:var(--surface); }     /* keep top tier white */
[data-testid="stExpander"]{ background:var(--surface-2); } /* nested content sits one step down */
```
*Linear (elevation band), Geist (shadow-as-border + ambient). The inset `0 0 0 1px` layer lets us soften or drop some literal 1px borders later without losing crispness on the cool `#f6f7f9` page.*

---

## Risks / anti-patterns to avoid

- **Don't add load-time animation.** Streamlit re-executes the script on every interaction, so any `@keyframes` that runs on element mount will replay on each rerun and read as nervous. Confine motion to `:hover`/`:active`/`:focus-visible` and to `:target` (which only fires on navigation). The citation flash and the active-press are safe; entrance fades and looping shimmers are not.
- **Don't multiply accent colors.** Linear's lesson is rationing. Keep the single deep-teal `#0e7490` for actions/links and the three evidence tones for evidence *only* — resist using amber/red anywhere decorative, or the markers lose their clinical signal.
- **Watch amber contrast.** `#a9781b` as small text on white is near the 4.5:1 line; keep it for swatches/large numerals, and if it ever becomes body-sized text, darken to ~`#946a14` (Stripe's "five levels apart" discipline).
- **Don't let `--faint` (`#8a96a2`) carry meaning.** It's below comfortable small-text contrast on white; use it only for truly secondary labels (disclaimers, tag eyebrows), never for content a clinician must read.
- **Don't chase the hover-preview citation card.** It's gorgeous on Perplexity/Granola but requires JS to position a floating card over Streamlit-rendered markdown; the anchor-scroll + `:target` flash delivers ~80% of the value at ~5% of the fragility.
- **Don't over-shadow.** Refactoring UI's warning: harsh/large shadows on every surface flatten hierarchy. Reserve the heavy ambient layer (`--shadow`) for genuinely floating things (metric cards, panels); keep rows and inline chips border-only.
- **Don't break the serif reading column.** Keep answers/claims/standfirst in Source Serif 4 and resist setting body copy in Archivo for "consistency" — the serif/sans/mono role split is the system's identity (NYT-grade pairing) and is doing real legibility work.

---

### Sources fetched directly
- Emil Kowalski — 7 Practical Animation Tips: https://emilkowal.ski/ui/7-practical-animation-tips
- Rauno Freiberg — Web Interface Guidelines: https://github.com/raunofreiberg/interfaces · https://interfaces.rauno.me/
- Shape of AI — Citations pattern: https://www.shapeof.ai/patterns/citations
- Stripe — Designing accessible color systems: https://stripe.com/blog/accessible-color-systems
- Linear — How we redesigned the Linear UI: https://linear.app/now/how-we-redesigned-the-linear-ui

### Sources via search (real URLs, snippet-level)
- Perplexity citations case study: https://www.aiuxplayground.com/gallery/perplexity-citations/
- OpenEvidence: https://www.openevidence.com/ · https://research.contrary.com/company/openevidence
- Glass Health API / evidence keying: https://glass.health/api-documentation
- Consensus vs Elicit (Consensus Meter, Q1–Q4 filters): https://paperguide.ai/blog/elicit-vs-consensus/
- Elicit (NIH review): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10089336/
- Linear design analysis: https://blog.logrocket.com/ux-design/linear-design/
- Stripe design (Behind the Gradient): https://uwux.medium.com/behind-the-gradient-design-at-stripe-476dcf61a51a
- Mintlify documentation design: https://www.saasframe.io/examples/mintlify-documentation
- Vercel Geist materials: https://vercel.com/geist/materials
- UpToDate GRADE grading guide: https://www.wolterskluwer.com/en/solutions/uptodate/policies-legal/grading-guide
- DynaMed editorial/evidence process: https://about.ebsco.com/clinical-decisions/dynamed-solutions/about/evidence-based-process/editorial-process
