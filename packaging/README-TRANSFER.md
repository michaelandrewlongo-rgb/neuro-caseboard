# Transferring neuro-caseboard to a Mac

`neuro-caseboard` is **not a single folder** — it's a 5-layer system. Only the code lives in
the repo; the rest lives elsewhere on disk and must travel too. This bundle packages all of
it; `setup-mac.sh` rebuilds it on the far side.

| Layer | Source (on the build machine) | Size | Travels as |
|---|---|---|---|
| Code (this repo, incl. `.git` + your WIP) | `~/projects/neuro-caseboard` | ~14M | `code/neuro-caseboard-repo.tar` |
| caseprep (external dep, pinned sha) | `~/projects/caseprep` | tiny tree | `code/caseprep-src.tar.gz` (git-free install on the Mac); GitHub pin is the fallback |
| Textbook index (LanceDB) | `~/neuro-textbook-rag/index` | ~970M | `data/textbook-index.tar` |
| Figure assets (page images, ~20k files) | `~/neuro-textbook-rag/assets` | ~15G | `data/textbook-assets.tar` |
| Board-review cards (LanceDB) | `~/projects/abns-board-review-lancedb` | ~347M | `data/abns-cards-lancedb.tar` |
| `uv` runtime (carries its own Python) | downloaded at build time | ~35M | `bin/uv` (macOS arm64) — why the Mac needs no pre-setup |

**Not packaged on purpose:**
- The **Python `.venv`** — its compiled wheels are Linux-x86_64; the Mac is arm64. Rebuilt by `setup-mac.sh`.
- The **HuggingFace model cache** (~3.5G needed) — re-downloaded on the Mac's first real query.
- **Secrets** (`ANTHROPIC_API_KEY`, GCP credentials, `NCBI_API_KEY`) — re-established on the Mac.
- **Source PDFs** (`/mnt/d/textbook_pdfs`) — only needed to *rebuild* the index, never to *run*.

---

## Step 1 — build the bundle (on the WSL/Linux machine)

Plug in the external drive, then point the staging script at its mount (so the 16G is written
straight to the drive, not copied twice):

```bash
cd ~/projects/neuro-caseboard
packaging/make-bundle.sh /mnt/<DRIVE>/caseboard-bundle
```

Preview the plan and sizes first, without writing the big tarballs:

```bash
DRY_RUN=1 packaging/make-bundle.sh /mnt/<DRIVE>/caseboard-bundle
```

The script verifies each source layer exists, checks free space, tars everything, and writes a
`SHA256SUMS` manifest (skip with `SKIP_CHECKSUM=1`). Eject the drive when it finishes.

## Step 2 — install on the Mac (no pre-setup, no Terminal)

**No prerequisites.** The bundle ships a self-contained `uv` runtime (`bin/uv`) that brings its
own Python, and the code is restored from a tarball — so there's no Homebrew, no system Python,
and no git to install. Just:

1. Open the drive's bundle folder and **double-click `Install Caseboard.command`**
   (if macOS blocks it: **right-click → Open → Open**, one time).
2. Wait ~10–15 min (needs Wi-Fi) until it shows **✅ INSTALLED**.

It restores the repo to `~/projects/neuro-caseboard`, extracts the data to its default home
paths, builds the `.venv` via uv, installs caseprep (from the bundled tree) + the project with
all extras, seeds `.env`, drops a **`Caseboard` shortcut on the Desktop**, and verifies the
install. Re-runnable; set `FORCE=1` to reinstall from scratch. `QUICKSTART.txt` is the same
steps on one page for a non-technical user.

## Step 3 — run it (and optionally add keys)

**Double-click `Caseboard` on the Desktop** → it opens the web app in your browser. That's it.
The USB can be unplugged after Step 2.

The **first** question downloads ~3.5G of models from HuggingFace and runs on **CPU/MPS**
(a Mac has no CUDA) — correct, just slower than the desktop GPU. It works with **no keys** (the
Explorer falls back to the deterministic path). For the smartest answers, open
`~/projects/neuro-caseboard/.env` and paste in `ANTHROPIC_API_KEY` and/or `GOOGLE_CLOUD_PROJECT`
(the latter also needs `gcloud auth application-default login` if you have the gcloud CLI).

---

## Notes & overrides

- **Less than everything?** Set `EXTRAS=web,llm,vertex,dev` before `setup-mac.sh` to skip the
  heavy `models` extra (no `torch`/`open-clip` download) if you only want the text path.
- **Custom locations** are honored end-to-end: `make-bundle.sh` reads `TEXTBOOK_HOME`,
  `CARDS_DIR`, `CASEPREP_DIR`; `setup-mac.sh` reads `TARGET_REPO`, `TEXTBOOK_HOME`, `PROJECTS`.
  If you extract data off the defaults, uncomment the path block in `.env`.
- **caseprep pin** (`8b1d8fd…`) is kept in lockstep with `ci/install.sh` and
  `.github/workflows/ci.yml`; override with `CASEPREP_REF` on either script.
- **Integrity:** if `setup-mac.sh` reports a checksum mismatch, the USB copy is corrupt —
  re-copy the bundle directory.
