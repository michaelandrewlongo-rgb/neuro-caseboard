"""Thin FastAPI wrapper over the existing neuro-caseboard engine (NEW surface).

This package adds a local HTTP API over the SAME engine the CLI and Streamlit app call.
It does not reimplement retrieval/RAG/PubMed — it imports and forwards. See api/server.py.
"""
