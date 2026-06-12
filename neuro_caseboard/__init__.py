"""neuro-caseboard: a unified neurosurgical case-prep dossier.

Composition layer over CasePrep (audited Explorer->Enricher->Auditor pipeline) and
textbook-rag (citation-grounded retrieval + figure lane). Owns a corrected report
model and Markdown/PDF renderers that fix the presentation defects of the legacy
CasePrep exporter. Topic-agnostic across the breadth of neurosurgery.
"""

__version__ = "0.1.0"
