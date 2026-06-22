# Plan — P0 #3: Ask-path content-bleed / hallucination guard

**Goal:** Catch the cross-source term bleed the eval found — a left-insular-glioma Ask answer asserting
"cavernoma" (a term from a *different* retrieved source) inside the Transsylvian-Approach paragraph.

**Root cause (traced):** `neuro_caseboard/answer_verify.py::verify_answer` checks each cited sentence
with `entailment.should_cite`, which is **recall-based** (LexicalVerifier: "does the premise cover
enough of the claim's tokens?"). A single bled entity inside an otherwise-grounded sentence passes
because the *other* tokens satisfy recall. Uncited sentences (no `[n]`) are auto-`supported=True`
(answer_verify.py:67-68). So a salient off-source entity like "cavernoma" rides along unflagged.
`guard.py` is the **Build-path** manifest pruner (posterior-fossa terms) — it does NOT touch Ask
synthesis, so the fix belongs in the Ask verification path, not guard.py.

**Approach (precision check on salient medical entities — low false-positive):** a term bearing a
medical suffix (`-oma|-itis|-osis|-ectomy|-otomy|-ostomy|-plasty|-pathy|-plegia|-paresis|-algia|-emia|
-cele|-rrhage|-rrhea|-stenosis`, etc.) asserted in a CITED claim must actually appear in THAT claim's
cited premise. If a medical-entity token in the claim is absent from its cited premise → the claim is a
bleed → mark unsupported (soft downgrade to needs-verification, never silent deletion — matches the
gate's conservative philosophy). Generic words never match the suffix set, so legitimate grounded
claims are untouched.

---

- [x] **Step 1 — Salient-medical-entity bleed check in the Ask verification path**
  - Add a helper (in `neuro_caseboard/entailment.py`, reusing `_TOKEN`/`_content_tokens`):
    `medical_entities(text) -> set[str]` = tokens matching the medical-suffix regex above (len ≥ 6 to
    avoid short coincidences). And `unsupported_entities(claim, premise) -> set[str]` = entities in the
    claim absent from the premise's tokens.
  - In `answer_verify.py::verify_answer`: for each CITED claim, after the existing `should_cite` check,
    ALSO compute `unsupported_entities(claim_text, premise)`. If non-empty, mark the claim
    `supported=False` (bleed) even if recall passed. (Keep the existing recall behavior as the first
    gate; this only ADDS rejections — never rescues.) Record the bleed entities on the verdict so the
    notice can name them.
  - Extend `ClaimVerdict` with `bleed_terms: list` (default empty) and have `verification_notice` /
    `verification_to_dict` surface them (e.g. "⚠ N claim(s) assert a term not in the cited source:
    cavernoma").
  - Tests `tests/test_bleed_guard.py` (NEW): (a) a claim "...transsylvian approach... cavernoma [2]"
    with premise[2] = a glioma/insula passage lacking "cavernoma" → claim flagged unsupported, bleed
    term = {"cavernoma"}; (b) NON-regression: a claim asserting "glioma [2]" with premise[2] mentioning
    "glioma" → NOT flagged; (c) a claim with no medical-entity tokens → unchanged behavior; (d) a claim
    whose entity is present in the premise (grounded) → not flagged.
  - Keep `tests/test_answer_verify.py`, `tests/test_entailment_gate.py`, `tests/test_guard.py` green.
  - **Verify:** `PYTHONPATH=vendor/caseprep pytest -q tests/test_answer_verify.py tests/test_entailment_gate.py tests/test_guard.py tests/test_bleed_guard.py`.

**Known limitation (ponytail, note in PR):** exact-token match means a premise synonym ("cavernous
malformation") wouldn't satisfy an answer's "cavernoma" → a rare soft false-positive (needs-verification
flag, never deletion). Upgrade path: synonym/lemma normalization. Acceptable for a conservative guard.
