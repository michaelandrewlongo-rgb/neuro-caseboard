"""Live literature lane: append a current-literature finding to a clinician answer.

For an arbitrary question this (1) reuses the textbook answer already computed
(stance + the top citation's book), (2) LLM-generates a PubMed query from the
question, (3) reuses engine.reconcile's search_and_rank + judge_stance, and
(4) returns a LiteratureFinding to attach to the QueryResult.

It NEVER raises into the answer path: any failure -> literature=None, so the
grounded textbook answer always stands.
"""
import json
import re

# Allowed pub-type bias (mirrors the curated topics; PubMed Publication Type values).
_ALLOWED_PUB_TYPES = ["Randomized Controlled Trial", "Meta-Analysis",
                      "Practice Guideline"]

QUERY_GEN_SYSTEM_PROMPT = (
    "You convert a clinician's question into a PubMed search. Return ONLY a JSON "
    "object, no prose, with keys:\n"
    '  "terms": a PubMed query string. Prefer a few key concepts joined with OR; '
    "avoid long AND-chains (PubMed ANDs every word, which over-narrows and returns "
    "nothing).\n"
    '  "pub_types": a list (possibly empty) chosen ONLY from '
    f'{json.dumps(_ALLOWED_PUB_TYPES)}, biasing '
    "toward high-quality evidence when the question is therapeutic.\n"
)


def _parse_query(text):
    """Extract {terms, pub_types} from the model reply or raise ValueError."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in query-gen reply")
    try:
        obj = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e
    terms = str(obj.get("terms") or "").strip()
    if not terms:
        raise ValueError("query-gen produced empty terms")
    raw = obj.get("pub_types", [])
    pub_types = [pt for pt in (raw if isinstance(raw, list) else [])
                 if pt in _ALLOWED_PUB_TYPES]
    return terms, pub_types


def build_pubmed_query(question, synth_client):
    """LLM-generate (terms, pub_types) from a free-text clinical question.

    Raises ValueError if the reply is not usable JSON with a non-empty terms string."""
    reply = synth_client.generate(QUERY_GEN_SYSTEM_PROMPT, question, [])
    return _parse_query(reply)
