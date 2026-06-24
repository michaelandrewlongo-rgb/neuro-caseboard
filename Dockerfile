# syntax=docker/dockerfile:1
# Multi-stage SERVE image for neuro-caseboard. This is the runtime/serve target — DISTINCT from
# required CI (which deliberately omits torch). It legitimately includes .[models] (sentence-
# transformers + open-clip-torch) for query-time embedding against the LanceDB index, plus
# .[vertex] (google-genai) for Vertex synthesis. NO corpus, NO index, NO secrets are baked in;
# those are mounted/injected at runtime by docker-compose.yml.

# ---- Stage 1: build the React/Vite SPA -> /web/dist ----
FROM node:20-slim AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build            # tsc -b && vite build -> /web/dist

# ---- Stage 2: build a venv with the package + heavy runtime extras ----
FROM python:3.12-slim AS py-build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /src
# Most deps ship manylinux wheels (lancedb, pymupdf, numpy, pillow, torch, open-clip,
# sentence-transformers). build-essential is added defensively in case pip must compile a sdist;
# if the build proves it unneeded, the implementer may drop it to shrink the build stage.
# ponytail: build-essential kept for a clean first build; drop if `pip install` uses only wheels.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*
# Only the files pip needs to build/install the package (pyproject packages= list + readme +
# the in-tree vendored caseprep). NOT api/ (run from workdir) and NOT web (built in stage 1).
COPY pyproject.toml README.md ./
COPY neuro_caseboard ./neuro_caseboard
COPY neuro_core ./neuro_core
COPY vendor ./vendor
RUN python -m venv /opt/venv \
 && . /opt/venv/bin/activate \
 && pip install --upgrade pip \
 && pip install ".[vertex,models,briefing]"

# ---- Stage 3: slim runtime ----
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    NEURO_CASEBOARD_WEB_DIST=/app/web/dist \
    SYNTH_PROVIDER=vertex
WORKDIR /app
# libgomp1: the OpenMP runtime torch/open-clip load at QUERY time (slim base omits it). Without it
# /api/ask & /api/cards would 500 on first retrieval while /api/health still reports engine:true
# (the engine probe never imports torch), so the engine-only rollback gate wouldn't catch it.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=py-build /opt/venv /opt/venv
# Chromium for the HTML->PDF PDF path (the dark Signal render). The `briefing` extra put the
# `playwright` CLI in /opt/venv; this fetches a real Chromium + its system libs. Without it
# /api/build/pdf silently falls back to the fpdf2 brutalist renderer instead of the HTML theme.
RUN playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*
COPY api ./api
COPY --from=web-build /web/dist ./web/dist
EXPOSE 8001
# /api/health always returns 200 with honest booleans; a 200 proves the server + endpoint are up.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=8)" || exit 1
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8001"]
