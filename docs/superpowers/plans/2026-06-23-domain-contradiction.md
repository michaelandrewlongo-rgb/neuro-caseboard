# Plan — P2 #8: false domain-contradiction flags ("N papers contradict expected domain (vascular)")

**Bug:** Valid vascular claims are flagged `off_target` with "1 papers contradict expected domain
(vascular)". Two defects, both in `vendor/caseprep/caseprep/audit/card_auditor.py::_audit_card`:

1. **Ordering/threshold bug (the false positive).** The decision checks `if contradictions:` FIRST
   (line 283), before the positive domain-match check. So a paper that is *strongly* in the expected
   domain (`paper_domain == case_domain`, e.g. a vascular paper) is flagged off_target the instant it
   contains ONE substring contradiction term (`_DOMAIN_CONTRADICTIONS["vascular"]` = meningioma, glioma,
   schwannoma, gtr, …) — e.g. a vascular abstract mentioning "glioma" in a differential, or "GTR". The
   positive vascular signal is never weighed. This **directly violates the module's own design rule**
   (docstring): *"default to needs_review rather than falsely marking a claim as off_target. Reject a
   paper only when its clinical domain clearly contradicts the case."*

2. **"1 papers" pluralization.** `audit_reason` strings hardcode "papers" (lines 299, 307), so a single
   paper reads "1 papers". (Backlog #14 flagged this instance; fixed here since we're editing the line.)

**Fix (lazy, restores stated intent):**
- Gate off_target on `not domain_match`: a paper the detector already classifies as IN the expected
  domain cannot be "contradicting" it. Genuine off-target papers (different `paper_domain`, no positive
  match) with contradiction terms are still flagged.
- Pluralize the two `audit_reason` strings via a tiny `_plural(n, "paper")` helper (or inline).

---

- [x] **Step 1 — Threshold fix + pluralization in card_auditor.py**
  - `vendor/caseprep/caseprep/audit/card_auditor.py::_audit_card`: change the decision branch
    `if contradictions:` → `if contradictions and not domain_match:` so a paper in the expected clinical
    domain is NOT flagged off_target on a stray contradiction term. (A vascular paper mentioning "glioma"
    once now falls through to `supported` if it has term_overlap, else `needs_review` — never off_target.)
  - Add a module-level `def _plural(n: int, noun: str) -> str: return f"{n} {noun}" if n == 1 else
    f"{n} {noun}s"` and use it in BOTH audit_reason strings:
    `f"{_plural(len(supported), 'paper')} in matching clinical domain ({case_domain or 'unknown'})"` and
    `f"{_plural(len(off_target), 'paper')} contradict expected domain ({case_domain or 'unknown'})"`.
    (Grammar nit: "1 paper contradict**s**" — acceptable to leave verb as-is per ponytail; the count is
    the visible defect. If trivial, also fix the verb agreement, but do not over-engineer.)
  - `vendor/caseprep/tests/test_card_auditor_domain.py` (NEW): construct EnrichedCards (import the real
    type, or `types.SimpleNamespace` with the attrs `_audit_card` reads: `question`, `why_it_matters`,
    `target_file`, `section_key`, `compiler_slot`, `answerability`, `papers`, `confidence`,
    `enrichment_status="success"`). Papers are dicts `{"id","title","text_snippet"}` (text = title+snippet).
    - **False-positive fixed:** topic="ruptured anterior communicating artery aneurysm clipping"; one
      paper strongly vascular ("endovascular coiling and clipping of a ruptured ACoA aneurysm, thrombectomy
      for vasospasm") whose snippet ALSO mentions "glioma" once (a contradiction term). Assert
      `audit_status != "off_target"` (it was off_target pre-fix → this test FAILS without the change).
    - **Non-regression (genuine off-target):** same vascular topic; a paper that is clearly tumor
      ("awake craniotomy for glioma resection, gross total resection / GTR", no vascular terms) → assert
      `audit_status == "off_target"` still. (paper_domain=tumor, domain_match False, contradictions present.)
    - **Pluralization:** a case with exactly 1 supported paper → `audit_reason` contains "1 paper " (not
      "1 papers"); construct a 2-supported case → "2 papers".
  - Keep `vendor/caseprep/tests/test_scoring.py` + `test_fact_propagation.py` green (they touch off_target
    via a different fn — must not regress).
  - **Verify:** `cd <worktree> && PYTHONPATH=vendor/caseprep python3 -m pytest -q
    vendor/caseprep/tests/test_card_auditor_domain.py vendor/caseprep/tests/test_scoring.py
    vendor/caseprep/tests/test_fact_propagation.py`.

**Scope guard:** #8 only — the contradiction-decision false positive + this one pluralization instance.
Do NOT touch retrieval (#7, merged) or other "1 papers" sites (#14 mops up any remaining).

**Non-regression invariant:** preserves honest evidence auditing — genuinely off-domain papers are still
quarantined as off_target; the change only stops mislabeling in-domain papers, matching the auditor's
stated "default to needs_review, reject only on clear domain contradiction" rule. No fabrication.
