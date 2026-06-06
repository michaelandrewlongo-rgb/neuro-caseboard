# Neurosurgery Textbook RAG

Local, citation-grounded Q&A over a folder of neurosurgery textbooks. Embeddings
and reranking run locally on the GPU; only retrieved excerpts are sent to
OpenRouter for synthesis.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then add your OPENROUTER_API_KEY
```

## Build the index (one-time, re-run when books change)

```bash
python -m scripts.build_index
```

## Ask a question

```bash
python -m cli.ask "What is the normal range for intracranial pressure in adults?"
```

## Validate

```bash
python -m pytest -q -m "not integration"   # fast unit tests
python -m pytest -q                          # include lancedb integration
python -m eval.run_eval                      # retrieval gate
python -m eval.run_eval --synthesize         # synthesis gate (blinded review)
```

## Design

See `docs/superpowers/specs/2026-06-06-neuro-textbook-rag-design.md`.
Phase 2 (figure/atlas visual retrieval) attaches at the `engine.query` seam.
