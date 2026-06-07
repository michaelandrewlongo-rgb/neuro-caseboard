# Neurosurgery Textbook RAG

Local, citation-grounded Q&A over a folder of trusted neurosurgery textbooks.
Ask an on-the-job clinical question and get a concise answer synthesized **only**
from your books, with every claim tied back to *book → chapter → page*. The
system refuses when the answer isn't in the corpus and flags it when sources
disagree.

Text extraction, embeddings, and reranking all run locally (on the GPU). What
leaves the machine is only what's sent to the synthesis model (Vertex AI Gemini
by default): the retrieved passages — and, for visual questions, the page images
of the matched figures (see [Phase 2](#phase-2--figure-retrieval)). Never the
whole books, never the index.

> Decision-support reference tool, not a substitute for clinical judgment.

## How it works

```
PDFs ──▶ extract text + TOC chapters ──▶ page-exact word chunks
  (PyMuPDF)                               (≤600 words, 80 overlap)
                                                │
                                                ▼
                                   BGE-large-en-v1.5 embeddings
                                        stored in LanceDB
                                                │
        ┌───────────────────────────────────────┤
        ▼                                        ▼
  vector search                          full-text (FTS) search
        └──────────── reciprocal rank fusion ────┘
                                │
                                ▼
                BGE-reranker-v2-m3 cross-encoder (top 6)
                                │
                                ▼
          OpenRouter synthesis — cite every claim, refuse if
            not found, surface disagreements between books
```

- **Retrieval is hybrid:** dense vectors *and* a native FTS keyword index, fused
  by reciprocal rank fusion, so it catches both semantic matches and exact terms
  (drug names, eponyms, scale names).
- **Reranking** uses a cross-encoder to reorder the fused candidates before they
  reach the LLM, so the model sees the 6 best passages rather than 20 noisy ones.
- **Chapters come from each PDF's table of contents**, so citations land on a
  real chapter title, not just a page number.

## Requirements

- Python 3 with the packages in `requirements.txt`.
- A NVIDIA GPU is strongly recommended. Embedding the full corpus on CPU takes
  ~1 hour; on GPU it's minutes. Querying works on CPU but reloads the models
  (tens of seconds) each run.
- An [OpenRouter](https://openrouter.ai) API key for the synthesis step.
- A folder of textbook PDFs that **have real text layers** (this pipeline
  extracts text; it does not OCR scanned images).

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # then add your OPENROUTER_API_KEY and set CORPUS_DIR
```

On the first index build, the embedding model (~1.3 GB) downloads
automatically.

> On this machine the interpreter is `python3` — substitute it for `python` in
> the commands below if `python` isn't aliased.

## Build the index

One-time, and re-run whenever the books change:

```bash
python -m scripts.build_index
```

This reads every PDF in `CORPUS_DIR`, prints a per-book text-coverage report (an
ingest sanity gate), chunks, embeds, and writes the LanceDB index (vectors + an
FTS index) to `INDEX_DIR`.

## Ask a question

```bash
python -m cli.ask "What is the normal range for intracranial pressure in adults?"
```

The answer prints first, followed by the numbered sources:

```
Sources:
  [1] NeuroICU, Intracranial Pressure, p.212
  [2] Greenberg, ...
```

## Phase 2 — figure retrieval

Visual/anatomy questions (atlas plates, radiology figures) are answered by
attaching the matched **page images** to a multimodal Gemini call: the model both
*describes* the figure and answers in words — cited to book/chapter/page — and the
figure is shown back to you. This reuses the Phase 1 text retrieval; figure pages
are detected and rendered at index-build time and ride along on the normal hybrid
search.

**1. Authenticate to Vertex AI** (synthesis defaults to Vertex; switch to
OpenRouter with `SYNTH_PROVIDER=openrouter` to skip this):

```bash
gcloud auth application-default login
# then set GOOGLE_CLOUD_PROJECT in .env (and GOOGLE_CLOUD_LOCATION if not us-central1)
```

**2. Re-index** — required once, because the build now also detects figure pages
and renders them to `ASSETS_DIR`:

```bash
python -m scripts.build_index   # coverage report now also prints figure-page counts
```

**3. Run the figure gate** (does the right plate surface?):

```bash
python -m eval.figure_eval               # retrieval only
python -m eval.figure_eval --synthesize  # also print answers + figures for blinded review
```

Tune `eval/figure_answers.yaml` to your own corpus and known plates.

**4. Launch the viewer** — answer + figure thumbnails + citations, reachable from
your phone on the same network:

```bash
streamlit run app/streamlit_app.py --server.address 0.0.0.0
```

### Figure-retrieval limitations

- **Whole-page display**, not a tight crop — the caption and figure travel together.
- **Phase 2a retrieval is text-driven** (caption/label text on the page), so a
  caption-less, purely-visual page can be missed. **Phase 2b** (below) adds a
  visual retrieval lane that fixes this.

## Phase 2b — visual retrieval

Phase 2a ranks figure pages by their page *text*, so pure-atlas plates (e.g.
Fukushima) can lose to text-dense operative books even when their image is the
better answer. Phase 2b adds a **local visual retrieval lane**: every figure page
is embedded with a CLIP-family model (`VISUAL_MODEL`, swappable) into a `figures`
table; at query time the question is embedded with the CLIP text tower,
image-searched, and the visual hits are **RRF-fused** with the text-figure hits to
choose which figures get attached. The worded answer is unchanged — only figure
selection improves. A figure surfaced only by image search becomes an appended
citable source. Image embeddings stay on-box; only query-time synthesis uses Vertex.

**1. Build the visual index** — no full re-index needed; this reuses the figure
PNGs already rendered by the Phase 2a build:

```bash
python -m scripts.build_visual_index
```

**2. A/B the lane** on the figure gate:

```bash
VISUAL_RETRIEVAL=off python -m eval.figure_eval   # Phase 2a text-only baseline
python -m eval.figure_eval                          # with the visual lane
```

**3. Model bake-off** — the default is BiomedCLIP; compare against SigLIP and keep
the winner in `.env`:

```bash
VISUAL_MODEL='hf-hub:timm/ViT-SO400M-14-SigLIP-384' python -m scripts.build_visual_index
VISUAL_MODEL='hf-hub:timm/ViT-SO400M-14-SigLIP-384' python -m eval.figure_eval
```

The figure gate evaluates the actual fused (text+visual) figures the system would
attach. Tune `eval/figure_answers.yaml` to your corpus (encode the genuinely
correct source — don't game it to pass).

### Visual-retrieval limitations
- **Whole-page embedding** (reuses the rendered PNGs), so a small figure on a
  text-heavy page embeds muddily — but those are text-findable anyway. Per-figure
  cropping is the documented next refinement.
- A general/biomedical CLIP may be imperfect on surgical line-drawings — mitigated
  by `VISUAL_MODEL` swappability and the bake-off.

## Configuration

Settings load from `.env` (CRLF is stripped automatically), then environment
variables override the file, then built-in defaults in `engine/config.py` apply.

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Required for synthesis |
| `OPENROUTER_MODEL` | `anthropic/claude-sonnet-4.6` | Synthesis model (swappable) |
| `CORPUS_DIR` | `/mnt/d/textbook_pdfs` | Folder of source PDFs |
| `INDEX_DIR` | `~/neuro-textbook-rag/index` | Where the LanceDB index lives |
| `EMBED_MODEL` | `BAAI/bge-large-en-v1.5` | Local embedding model |
| `RERANK_MODEL` | `BAAI/bge-reranker-v2-m3` | Local cross-encoder reranker |
| `EMBED_DEVICE` | `auto` | `auto` → CUDA if available, else CPU |
| `RETRIEVE_K` | `20` | Candidates pulled per retriever before fusion |
| `RERANK_K` | `6` | Passages kept after reranking, sent to the LLM |
| `CHUNK_MAX_WORDS` | `600` | Max words per chunk |
| `CHUNK_OVERLAP_WORDS` | `80` | Overlap between adjacent chunks |
| `SYNTH_PROVIDER` | `vertex` | `vertex` (Vertex AI Gemini) or `openrouter` |
| `GOOGLE_CLOUD_PROJECT` | — | GCP project (required when provider is `vertex`) |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | Vertex region |
| `VERTEX_MODEL` | `gemini-2.5-flash` | Vertex multimodal synthesis model |
| `MAX_FIGURE_IMAGES` | `5` | Max figure-page images attached per query (cost cap; also the # of fused text+visual figure slots) |
| `FIGURE_DPI` | `160` | Render DPI for figure pages |
| `FIGURE_AREA_THRESHOLD` | `0.1` | Min image area fraction to count a page as a figure |
| `ASSETS_DIR` | `~/neuro-textbook-rag/assets/figures` | Cached figure-page PNGs |
| `VISUAL_MODEL` | `hf-hub:microsoft/BiomedCLIP-...` | Local CLIP model for the visual lane (swappable) |
| `VISUAL_RETRIEVE_K` | `10` | Figure-page candidates from the visual lane before fusion |
| `VISUAL_RETRIEVAL` | `true` | Turn the visual retrieval lane on/off (A/B) |

### Synthesis model

**The default provider is now Vertex AI Gemini** (`SYNTH_PROVIDER=vertex`,
`VERTEX_MODEL=gemini-2.5-flash`) so synthesis — including multimodal figure
reading — runs on GCP (and can draw on GCP credit). Set
`SYNTH_PROVIDER=openrouter` to fall back to the OpenRouter path described next.

When `SYNTH_PROVIDER=openrouter`, `OPENROUTER_MODEL` is the knob that sends data
off-box, and it's freely
swappable. The repo default in `config.py` is `anthropic/claude-sonnet-4.6`. The
active `.env` uses `google/gemini-3-flash-preview`, chosen for value (~6× cheaper
per question) after a blinded check confirmed it answered in-domain clinical
queries correctly, cited every claim, flagged source disagreement, and abstained
honestly on an off-domain query. (Minor quirk: Gemini occasionally emits LaTeX
like `$\ge$`.) Swap in any OpenRouter model by editing `.env`.

## Validation

```bash
python -m pytest -q -m "not integration"   # fast unit tests
python -m pytest -q                          # include the LanceDB integration test
python -m eval.run_eval                      # retrieval gate (does the right book surface?)
python -m eval.run_eval --synthesize         # also print answers for blinded review
```

The retrieval gate (`eval/known_answers.yaml`) checks that known questions pull
the expected book to the top — tune its expected book names to your own corpus.

## Project layout

```
engine/          # the RAG core — single query(question) -> {answer, citations} seam
  ingest.py      #   PDF text + TOC-derived chapters (PyMuPDF)
  chunk.py       #   page-exact word chunking
  embed.py       #   local BGE embeddings
  index.py       #   LanceDB build + hybrid (vector + FTS) search, RRF
  rerank.py      #   BGE cross-encoder reranking
  figures.py     #   figure-page detection, caption, page→PNG rendering
  visual_embed.py  # local CLIP image/text embedder (open_clip, swappable)
  visual_index.py  # `figures` table build + image_search (visual lane)
  synthesize.py  #   multimodal synth: passages (+figure images), cite-or-refuse
  synth_clients.py #  Vertex / OpenRouter adapters + provider select
  query.py       #   wires it together; RRF-fuses text+visual figure selection
  config.py      #   .env / env / defaults
cli/ask.py       # thin command-line entry point
app/streamlit_app.py  # minimal web viewer (answer + figures + citations)
scripts/build_index.py        # full build (text index + visual index)
scripts/build_visual_index.py # visual index only, over already-rendered PNGs
eval/            # retrieval + figure + synthesis gates
tests/           # unit tests + real LanceDB integration tests
docs/superpowers/  # design spec and implementation plan
```

The whole pipeline sits behind one seam — `engine.query(question)` — so the CLI
is thin and future front-ends (or Phase 2 figure retrieval) attach without
reworking the core.

## Data boundary

- Books, embeddings, and the index never leave the machine.
- Each query sends only the top-ranked retrieved excerpts (plus your question)
  to the configured synthesis model (Vertex AI Gemini by default).
- **For visual questions, the page images of the matched figures are also sent**
  (capped by `MAX_FIGURE_IMAGES`). Those are rendered pages of copyrighted
  textbooks — factor that in when choosing the provider.
- The system prompt constrains the model to answer **only** from the supplied
  passages and to say *"Not found in the provided sources."* otherwise.

## Known limitations

- **Index build isn't crash-resumable** — it re-embeds from scratch and only
  swaps in the new index at the very end.
- **The printed citation list shows all retrieved passages**, not only the ones
  the model actually cited inline.

## Roadmap

- **Phase 2a — figure retrieval: implemented** (see
  [Phase 2 — figure retrieval](#phase-2--figure-retrieval) above).
- **Phase 2b — visual retrieval lane: implemented** (see
  [Phase 2b — visual retrieval](#phase-2b--visual-retrieval) above). Atlas plates
  surface on image similarity, RRF-fused with the text lane.
- **Phase 2c — phone/web layer: implemented.** A FastAPI server (`server/main.py`)
  wraps `engine.query` and serves an installable phone-first PWA (`webapp/`, Layout A).
  Retrieval + corpus stay local in WSL2; synthesis runs on Vertex `gemini-2.5-pro`.
  Launch with `scripts/serve.sh`; reach it from your phone over Tailscale after a
  one-time `scripts/setup-wsl-bridge.ps1` on the Windows host. See
  [Phase 2c — phone/web app](#phase-2c--phoneweb-app) below.
- **Per-figure crops: deferred refinement**, to add only if whole-page visual
  embedding proves muddy on small-figure pages.

## Phase 2c — phone/web app

A FastAPI server wraps the same `engine.query` seam and serves an installable,
phone-first PWA so you can ask from your phone on the floor. Retrieval and the
copyrighted corpus stay on the workstation; only the answer reaches your device, over
your private Tailscale network.

Run it inside WSL2:

```bash
./scripts/serve.sh            # serves on 0.0.0.0:8000; engine warmed once at startup
```

One-time Windows bridge (so the phone can reach the WSL2 port via the host's Tailscale
interface) — run in an elevated PowerShell on the Windows host:

```powershell
./scripts/setup-wsl-bridge.ps1   # netsh portproxy + firewall allow; re-run after a reboot
```

Then open `http://<your-PC-tailscale-ip>:8000` on your phone and, in Safari, use
**Share → Add to Home Screen** to install it. The screen is Layout A: an answer with
tappable `[n]` citations → figures (tap for full-screen) → sources; recent-question
history and copy/share are built in. Synthesis runs on Vertex `gemini-2.5-pro`
(`SYNTH_PROVIDER=vertex`, `VERTEX_MODEL=gemini-2.5-pro`), billed to your Google Cloud
credit.

## Design docs

- Spec: `docs/superpowers/specs/2026-06-06-neuro-textbook-rag-design.md`
- Plan: `docs/superpowers/plans/2026-06-06-neuro-textbook-rag.md`
- Phase 2 spec: `docs/superpowers/specs/2026-06-06-neuro-textbook-rag-phase2-figure-retrieval-design.md`
- Phase 2 plan: `docs/superpowers/plans/2026-06-06-phase2-figure-retrieval.md`
- Phase 2b spec: `docs/superpowers/specs/2026-06-06-neuro-textbook-rag-phase2b-visual-retrieval-design.md`
- Phase 2b plan: `docs/superpowers/plans/2026-06-06-phase2b-visual-retrieval.md`
- Phase 2c spec: `docs/superpowers/specs/2026-06-07-neuro-textbook-rag-phase2c-phone-web-layer-design.md`
- Phase 2c plan: `docs/superpowers/plans/2026-06-07-phase2c-phone-web-layer.md`
