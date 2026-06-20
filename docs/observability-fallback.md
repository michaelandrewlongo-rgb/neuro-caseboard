# Observable LLM fallback

The case-board build path emits a typed `Provenance` (`neuro_caseboard/model.py`) set at the
LLM-vs-deterministic decision point in `pipeline._resolve_manifest`. When the LLM lane is
requested but unavailable, the board falls back to the deterministic Explorer and:

- `Dossier.provenance.degraded` is True, carrying a PHI-safe `reason`
  (`llm_error` | `llm_underproduced`) and `detail` (exception type only).
- A WARNING is logged on `neuro_caseboard.pipeline` (reason codes/counts only — never card or
  topic text).
- A fallback banner renders on every surface: markdown, the exec-Navy PDF, the fpdf2 PDF, the
  CLI build summary, and the Streamlit Build lane.

An explicitly-chosen deterministic run (`--no-llm`, or `CASEBOARD_LLM=0`) is **not** degraded:
`reason="llm_disabled"`, no banner, no WARNING — the CLI still prints the `Explorer:` source
line so provenance is always visible.

Two detection layers guard schema drift:
- **Runtime (graceful + loud):** `explore_llm.author_cards` logs a WARNING with card counts when
  the model returns enough cards but most are rejected by `_coerce_cards` (the drift signature).
  Control flow is unchanged — the board still degrades gracefully.
- **Dev-time (fail loud):** `tests/test_explore_llm.py::test_prompt_section_keys_match_validator`
  fails CI if the AUTHOR/CRITIC prompt's `_SECTION_KEYS` and the validator `_SLOTS_BY_FILE` ever
  diverge — a covert/careless schema edit cannot silently disable the AI lane.

## Known follow-ups (out of scope for v1)
- The **case path** (`build_case_manifest` / `build_case_dossier`) has the same silent fallback
  and is not yet instrumented. The plumbing here (`Provenance`, `fallback_notice`, renderer
  banners, `compile_case_dossier(provenance=)`) is ready for it; wire `build_case_dossier` to
  compute provenance the same way `build_dossier` does.
- A **fallback-rate metric/alert** was deliberately deferred — there is no metrics sink today.
  Revisit if the tool becomes multi-user/served.
