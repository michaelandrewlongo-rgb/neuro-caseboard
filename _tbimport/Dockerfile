# Cloud Run image for the Neuro Textbook RAG Streamlit app.
# Single-query inference runs on CPU (the GPU was only ever needed to BUILD the
# index). The 332 MB index is baked in; the 7.6 GB figures are mounted from GCS
# at runtime at the absolute path the index stored (/home/michael/...).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# CUDA torch (for Cloud Run L4 GPU). Falls back to CPU automatically when no GPU
# is present because EMBED_DEVICE=auto -> resolve_device() checks torch.cuda.
RUN pip install torch torchvision

COPY requirements.txt .
RUN pip install -r requirements.txt

# Pre-bake the three models into the image so the first query doesn't download them.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('BAAI/bge-large-en-v1.5'); CrossEncoder('BAAI/bge-reranker-v2-m3')"
RUN python -c "import open_clip; open_clip.create_model_from_pretrained('hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224')"

# App code + prebuilt index. Figures come from the mounted GCS bucket at runtime.
COPY engine/ engine/
COPY app/ app/
COPY index/ index/

ENV EMBED_DEVICE=auto \
    INDEX_DIR=/app/index \
    ASSETS_DIR=/home/michael/neuro-textbook-rag/assets/figures \
    SYNTH_PROVIDER=vertex \
    VERTEX_MODEL=gemini-2.5-pro \
    GOOGLE_CLOUD_LOCATION=us-central1 \
    VISUAL_RETRIEVAL=true

EXPOSE 8080
# Cloud Run injects $PORT. CORS/XSRF are disabled because the app runs behind
# Cloud Run's managed HTTPS proxy and is gated by APP_PASSWORD.
CMD streamlit run app/streamlit_app.py \
    --server.port ${PORT:-8080} --server.address 0.0.0.0 --server.headless true \
    --server.enableCORS false --server.enableXsrfProtection false \
    --browser.gatherUsageStats false
