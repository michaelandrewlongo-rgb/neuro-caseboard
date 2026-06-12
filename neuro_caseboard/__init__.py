"""neuro-caseboard: a unified neurosurgical case-prep dossier.

Composition layer over CasePrep (audited Explorer->Enricher->Auditor pipeline) and
textbook-rag (citation-grounded retrieval + figure lane). Owns a corrected report
model and Markdown/PDF renderers that fix the presentation defects of the legacy
CasePrep exporter. Topic-agnostic across the breadth of neurosurgery. Clinical depth
comes from an LLM-first Explorer (case-specific question generation) with a deterministic
fallback and an anti-bleed guard.
"""

__version__ = "0.1.0"
