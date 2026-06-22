# Plan — Dossier quarantine claims + strict tab filter (P0 #1)

**Goal:** Surface quarantined claims as status-badged cards in the Dossier claim list, and make the
SUPPORTED / VERIFY / QUARANTINE tabs strictly *subset* the list (not merely dim non-matching claims).

**Root cause (confirmed):**
- `neuro_caseboard/compile.py` builds `Claim`s only from `primary` cards; `off_target` (quarantined)
  cards are routed to an appendix entry as plain text, never as `Claim`s. So `EvidenceSummary.quarantined`
  counts them but they have no badge and the claim list never contains them.
- `web/src/lib/api.ts` `DossierClaim.status` is `"supported" | "verify"` — no `"quarantine"` member.
- `web/src/components/build/DossierView.tsx` `claimMatchesFilter` returns `false` for the `quarantine`
  filter, and tabs apply opacity (`dimmed`) instead of subsetting the rendered list.

**Two independent steps** — Step 1 is pure-Python (engine emits quarantine claims), Step 2 is pure-TS
(frontend renders + strictly subsets them). Each is fully verified by the existing 3-command harness.

**Non-regression invariants (do not break):** quarantine still counted in `EvidenceSummary.quarantined`;
"Rejected Sources (off-target)" and "Evidence Sources" appendix entries unchanged; existing
`test_compile.py` (37) and web vitest (20) stay green; renderers (md/pdf) still render for the new status.

---

- [x] **Step 1 — Engine: emit quarantined cards as `status="quarantine"` claims (Python)**
  - `neuro_caseboard/model.py`: register the new status so renderers don't blank-render it.
    - `MARK`: add `"quarantine": "✗"`. `ASCII_MARK`: add `"quarantine": "[QUARANTINE]"`.
    - `LEGEND_ITEMS`: append `("quarantine", "off-target — excluded from synthesis")`.
    - Update the `Claim.status` comment to `"supported" | "verify" | "quarantine"`.
    - If `render_pdf.py` has a `_COLORS`/`glyph` map or `render_md.py` an evidence-summary line, add a
      quarantine entry/count there too (additive; both already use `.get(status, default)` so this is
      cosmetic completeness, not a correctness gate).
  - `neuro_caseboard/compile.py`: in the `for tf in ordered_tf` loop, AFTER the `for c in primary`
    block builds `claims`, add a loop over `quarantined` that appends one `Claim` per card with
    `status="quarantine"`, `text=scrub_question(c.question)`, `why=(c.audit_reason or "off-target
    retrieval — excluded from synthesis").strip()`, `raw=c.question`. Do NOT attach citation marks or
    grade to quarantine claims (they are off-target). These appends must happen before the
    `if claims or figures:` section-append check, so a tf with only quarantined cards still produces a
    section. REMOVE the now-redundant `if quarantined: appendix_entries.append(AppendixEntry(heading=…,
    items=…))` block (the quarantine cards are now claims; keep "Rejected Sources" / "Evidence Sources").
  - `tests/test_dossier_quarantine.py` (NEW): mirror `tests/test_compile.py`'s card/manifest
    construction. Build cards including ≥1 `audit_status="off_target"` card. Assert: (a) some
    `Section.claims` contains a `Claim` with `status == "quarantine"` and text derived from the
    off-target card's question; (b) the total count of `quarantine` claims across all sections ==
    `dossier.summary.quarantined`; (c) no `AppendixEntry` re-lists those quarantine questions as `items`
    (no double-listing). Keep supported/verify behavior assertions to prove non-regression.
  - **Verify:** `PYTHONPATH=vendor/caseprep python3 -m pytest -p no:cacheprovider -q tests/test_compile.py tests/test_dossier_quarantine.py` passes; `npm --prefix web run test` + `npm --prefix web run build` still green (TS untouched).

- [x] **Step 2 — Frontend: quarantine badge + strict subset filter (TypeScript)**
  - `web/src/lib/api.ts`: `DossierClaim.status: "supported" | "verify" | "quarantine"`.
  - `web/src/lib/claimFilter.ts` (NEW): export `type ClaimFilter = "all" | "supported" | "verify" |
    "quarantine"`; `claimMatchesFilter(status, filter): boolean` (quarantine filter ⇒ `status ===
    "quarantine"`, all ⇒ true, else exact match); `subsetClaims<T extends {status}>(claims, filter): T[]`
    = `claims.filter(c => claimMatchesFilter(c.status, filter))`.
  - `web/src/components/build/DossierView.tsx`:
    - Import `ClaimFilter`, `claimMatchesFilter`, `subsetClaims` from `@/lib/claimFilter` (drop the
      local copies). Re-export `ClaimFilter` if `Build.tsx` imports it from here (preserve the existing
      import path — check and keep it compiling).
    - `statusMeta`: explicit 3-way — supported→green `#34e07f` "SUPPORTED"; verify→amber `#ffc94d`
      "TO VERIFY"; quarantine→red `#ff5a5a` "QUARANTINED", srLabel "off-target — excluded from
      synthesis".
    - `SectionCard`: compute `const visible = subsetClaims(section.claims, filter)`; render `visible`
      (NOT all claims with opacity). Remove the `dimmed`/`opacity` logic from `ClaimCard`. When
      `filter !== "all"` and `visible.length === 0`, render nothing for that section (hide it) so a tab
      strictly subsets the page rather than showing empty section shells.
  - `web/src/lib/claimFilter.test.ts` (NEW): cover every (status × filter) combination — especially
    quarantine matches only under the quarantine/all filters; `subsetClaims` returns only matching
    claims and preserves order.
  - **Verify:** `npm --prefix web run test` (incl. new spec) + `npm --prefix web run build` (union
    typechecks) green; `PYTHONPATH=vendor/caseprep python3 -m pytest … tests/test_compile.py tests/test_dossier_quarantine.py` still green.

---

## Review Findings (PR #56, increment 8)

- [MUST] `web/src/pages/Build.tsx`:500-515 / `compile.py`:198 — tab counts come from `EvidenceSummary`
  (card-level, PRE-dedup) but DossierView now strictly subsets POST-dedup claims → tabs over-count
  (verified: VERIFY shows (3) renders 2, ALL shows (7) renders 6 across all fixtures). Trust-breaking.
- [SHOULD] `compile.py`:185-198 — quarantine claims enter `claims` before `dedup_sections`, so an
  off-target claim can suppress a legitimate primary claim in a later section (Jaccard ≥ 0.72) → a real
  claim silently vanishes behind a cross-ref to off-target content.
- [SHOULD] `render_pdf.py`:132/139/301 — summary still reads "quarantined (appendix)" + omits the
  marker glyph; quarantine now renders inline, so "(appendix)" misdirects. render_md was updated; pdf wasn't.
- [SHOULD] `DossierView.tsx`:288 — clicking a 0-count tab blanks the main column (every SectionCard
  returns null) with no empty-state; QUARANTINE is routinely (0), so it reads as a broken page.
- [NIT] `compile.py`:120 vs :234 — emission uses `audit_status not in _PRIMARY`, gauge uses
  `== "off_target"`; equivalent only because the status domain is closed at 4 values. Use one predicate.
- [NIT] `render_md.py`:14 / `render_pdf.py`:114-115 legends are hardcoded 2-item and omit the ✗
  quarantine marker now shown on cards; `model.py` `LEGEND_ITEMS` quarantine entry is dead code (unconsumed).
- [NIT] `tests/test_dossier_quarantine.py`:36-42 — double-listing test passes vacuously (appendix uses
  `sources=` not `items=`); suite never asserts `rendered verify == summary.to_verify` (what let the MUST ship).

### Review tasks
- [ ] review: [MUST] derive tab counts from rendered (post-dedup) claims by status, not `summary.*` —
  compute via `subsetClaims(allClaims, filter).length` in Build.tsx (extract a pure helper); add a test
  asserting tab-count == rendered-count for supported/verify/quarantine/all.
- [ ] review: [SHOULD] `dedup_sections` skips `status == "quarantine"` (never a dedup victim, never added
  to `seen`) — prevents off-target claims suppressing legitimate primary claims.
- [ ] review: [SHOULD] `render_pdf.py` summary mirrors render_md (quarantine glyph + "(off-target)"); fix
  the "(appendix)" wording at the summary/legend lines so it no longer claims quarantine is in the appendix.
- [ ] review: [SHOULD] DossierView shows an empty-state ("no claims match this filter") when a filter
  yields zero claims across all sections.
- [ ] review: [nits] single quarantine predicate in compile.py; add ✗ to md/pdf legends (or drop dead
  `LEGEND_ITEMS`); make `test_no_appendix_double_listing` non-vacuous + add a `rendered==tab` assertion.
