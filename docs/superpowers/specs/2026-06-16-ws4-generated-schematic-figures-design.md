# Design — WS-4: Generated schematic figures (the headline)

- **Date:** 2026-06-16
- **Status:** Approved (locked by LOOP_PROMPT §4 WS-4 + §2); implementation in progress
- **Branch:** `worktree-streamlit-executive-navy-loop`
- **Loop:** Case Dossier engine, Pass 4 of 5 · builds on WS-1/2/3

## 1. Context & problem
The case dossier needs **generated schematics** that help conceptualize *this exact case* — the
corridor, the trajectory, the level/clip/anatomy — labeled, reproducible, and grounded. Locked
decisions (§2): an LLM emits a **structured figure spec** (JSON), and **deterministic Python drawing
code** renders a labeled diagram. No text-to-image / raster genAI. The spec may be LLM-authored; the
pixels must be deterministic from the spec.

## 2. Decisions
- **Renderer = PIL (`pillow`, already a core dep).** Deterministic `ImageDraw` over normalized
  coordinates with the repo's bundled DejaVu TTF → **byte-stable PNG** (same spec → identical bytes
  in-process), offline, **no new dependency**. (SVG considered; PNG chosen so the blind judge can
  open the artifact directly and it embeds in the existing PDF lane.)
- **Spec is a typed dataclass** (`FigureSpec`) with `from_dict` coercion (mirrors the LLM-JSON
  tolerance pattern). Archetypes: `corridor` (cranial/skull-base), `spine_level` (spine),
  `vessel_config` (vascular), `anatomy_map` (fallback). Nodes carry normalized x/y + label + kind;
  edges carry trajectory/relation; plus side/level/region + callouts + caption.
- **Author is LLM-first with a deterministic fallback** (same injected-`complete_fn` contract).
  Deterministic fallback picks the archetype from `classify_profile(case.to_topic())` and composes
  nodes/labels from the case's own geometry (side/level/target) — topic-agnostic, no hardcoded
  clinical content.
- **Guard reuses the anti-bleed logic.** `guard_spec(spec, case)` rejects a spec whose **side**,
  **level**, or **region** contradicts the `CaseContext` (level compare via
  `figure_guards._levels_in`; region via `figure_guards.figure_offtarget`). A rejected spec is
  dropped, never rendered.
- **Schematic, never a radiograph.** Every rendered figure carries a mandatory on-image banner and a
  `FigureItem.caption` beginning "Schematic (not a radiograph): …". Generated figures attach as
  `FigureItem`s alongside any retrieved plates.

## 3. Detailed design — `neuro_caseboard/figures_gen/`
### 3.1 `spec.py`
```python
@dataclass
class FigureNode: id: str; label: str; x: float; y: float; kind: str = "structure"
@dataclass
class FigureEdge: src: str; dst: str; kind: str = "relation"   # relation|trajectory|approach
@dataclass
class FigureSpec:
    archetype: str; title: str; side: str = ""; level: str = ""; region: str = ""
    nodes: list[FigureNode] = []; edges: list[FigureEdge] = []
    callouts: list[str] = []; caption: str = ""
    @classmethod
    def from_dict(cls, d) -> "FigureSpec": ...     # tolerant coercion; clamps x/y to [0,1]
ARCHETYPES = {"corridor","spine_level","vessel_config","anatomy_map"}
```

### 3.2 `guard.py`
```python
def guard_spec(spec, case) -> tuple[bool, str]:
    # reject when side set on both and differ (not bilateral/midline-compatible);
    # reject when level set on both and _levels_in disagree;
    # reject when figure_offtarget(spec.region/caption, case.to_topic()) flags cross-region.
def filter_specs(specs, case) -> list[FigureSpec]   # keep only guard-passing specs
```

### 3.3 `render.py`
```python
def render_spec(spec, *, width=900, height=640, font_path=None) -> bytes   # PNG bytes, deterministic
def render_spec_to_file(spec, path, **kw) -> str
```
Per-archetype layout helpers draw a titled frame, the mandatory "SCHEMATIC — NOT A RADIOGRAPH"
banner, nodes (labeled dots/boxes), edges (lines/arrows; trajectory dashed), a side/level chip, and a
callouts legend. Uses the bundled `assets/fonts/DejaVuSans*.ttf`; falls back to PIL's default font if
absent. No timestamps → byte-stable.

### 3.4 `author.py`
```python
FIGSPEC_SYSTEM = "...author 2-4 structured figure specs (JSON) for this case..."
def build_figure_specs(case, *, complete_fn=None, max_specs=4) -> list[FigureSpec]   # LLM-first + fallback
def deterministic_figure_specs(case) -> list[FigureSpec]   # archetype by profile, nodes from geometry
```

### 3.5 `__init__.py`
```python
def generate_case_figures(case, out_dir, *, complete_fn=None, start_index=1) -> list[FigureItem]:
    # author -> guard/filter -> render to <out_dir>/case-fig-NN.png -> FigureItem(
    #   fig_id="S{n}", image_path=..., caption="Schematic (not a radiograph): <title> ...",
    #   relevance=..., citation="generated schematic")
```

### 3.6 Pipeline integration — `pipeline.build_case_dossier(..., figures_dir=None, fig_complete_fn=None)`
When `figures_dir` is given, after compile + literature, call `generate_case_figures(case,
figures_dir, complete_fn=fig_complete_fn)` and append the FigureItems to the **"Case Figures"**
section (creating/attaching to it). Offline-safe (PIL core); no figures generated when `figures_dir`
is None (keeps existing tests/eval untouched). Retrieved textbook plates (when enrich on) are
unaffected.

## 4. Acceptance criteria (LOOP_PROMPT §5 WS-4)
- A contradictory-side/level spec is **rejected by the guard** in a unit test.
- Renders are **deterministic**: same spec → byte-identical PNG (in-process test).
- Generated figures attach as `FigureItem`s with a caption that says **schematic, not radiograph**.
- Blind **image-opening** judge ≥ 8/10 on conceptual correctness and ≥ 8/10 on case-specificity
  (right side/level) across cranial/spine/endovascular figure cases — **deferred to a keyed/visual
  judge run** (no provider/visual judge in this environment), but the eval renders real PNGs a judge
  can open, with `figure_spec_cases.json` ground truth.

## 5. Testing strategy (offline, deterministic)
- `tests/test_figure_spec.py`: `from_dict` coercion (clamps x/y, drops bad nodes, defaults).
- `tests/test_figure_guard.py`: contradictory side and contradictory level each rejected; an aligned
  spec passes; region cross-bleed rejected.
- `tests/test_figure_render.py`: `render_spec` returns a PNG (`\x89PNG` header), non-trivial size,
  and **byte-identical** on a second call; renders all four archetypes without error.
- `tests/test_figure_author.py`: injected fake JSON → specs across archetypes, invalid dropped;
  `deterministic_figure_specs` returns the profile-appropriate archetype + case-aligned side/level
  for spine/cranial/vascular; no hardcoded foreign clinical literal.
- `tests/test_case_figures.py`: `generate_case_figures(tmp_path)` writes PNG files + returns
  FigureItems whose caption starts "Schematic (not a radiograph)"; a contradictory spec is excluded.
- `tests/test_pipeline.py` (extend): `build_case_dossier(..., figures_dir=tmp)` attaches schematic
  FigureItems to the Case Figures section; without it, none (regression-safe).

## 6. EVAL
`eval/figure_spec_cases.json` (cranial/spine/vascular ground truth: expected archetype, side, level,
must-label terms). `eval/figure_spec_eval.py`: author (deterministic) → guard → render to
`eval/_fig_specs/<id>.png`; assert byte-stability + guard behavior + that the case's side/level
appear in the spec; write `eval/FIGURE_SPEC_REPORT_<date>.md` for a blind image judge. Live ≥8/10
image grade deferred (no visual judge here).

## 7. Risks
- **Byte-stability across environments** (Pillow/freetype versions) → scope the guarantee to
  in-process / same-environment (CI pins versions); the test renders twice in one process.
- **New dep creep** → none: PIL is core; matplotlib avoided. Author LLM stays behind injection.
- **Topic-agnostic** → deterministic specs compose from case fields + archetype templates; a
  no-foreign-literal test guards it. The guard enforces side/level/region grounding.
- **Schematic mistaken for imaging** → mandatory on-image banner + caption prefix; tested.

## 8. Out of scope
PDF embedding of schematics + CLI `caseboard case` + Streamlit lane (WS-5). No new runtime dependency.
