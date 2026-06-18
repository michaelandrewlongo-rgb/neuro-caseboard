#!/usr/bin/env python3
"""
Textbook Figures — VLM captioner / quality-filter (pgvector corpus).

Sibling to ``labeler.py`` (which serves the bank.db PMC figures).  This one
points the *same* neurosurgical labeling prompt at the ``textbook_figures``
table in the corpus Postgres DB, captioning + classifying directly from the
``image_data`` bytes.  Switches the model to Gemini 2.5 Flash.

For every figure it writes (additively — original columns are preserved):
  caption_vlm, vlm_modality, vlm_anatomy, vlm_pathology, vlm_procedure,
  vlm_keywords (JSON), is_neurosurgical, surgical_usefulness, vlm_model
…and backfills the original anatomical_region / procedure_approach /
figure_type ONLY where they are currently empty.

Idempotent: processes rows ``WHERE vlm_model IS NULL`` so an interrupted run
resumes cleanly.

Usage:
    python -m caseprep.image_bank.textbook_labeler --dry-run
    python -m caseprep.image_bank.textbook_labeler            # full run
    python -m caseprep.image_bank.textbook_labeler --limit 25 # small test batch
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import sys
from typing import Any

import httpx

# Reuse the proven neurosurgical labeling/filter prompt + key resolution verbatim.
from caseprep.image_bank.labeler import LABEL_PROMPT, OPENROUTER_API_KEY

# ── Constants ────────────────────────────────────────────────────────────────

LABEL_MODEL = "google/gemini-2.5-flash"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
CONCURRENCY = 20
MAX_RETRIES = 3
REQUEST_DELAY = 0.15
MAX_IMAGE_BYTES = 3_000_000  # skip/flag oversized blobs

_DB_URL_ENV = "PAPERS_CORPUS_DB_URL"
_DEFAULT_DB_URL = (
    "postgresql+psycopg://corpus_pipeline:corpus_pipeline@127.0.0.1:5432/corpus_pipeline"
)


def _db_kwargs() -> dict[str, Any]:
    url = os.environ.get(_DB_URL_ENV, _DEFAULT_DB_URL)
    m = re.match(r"postgresql(?:\+psycopg)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", url)
    if not m:
        raise ValueError(f"Unsupported DB URL: {url[:60]}")
    user, pwd, host, port, db = m.groups()
    return {"host": host, "port": int(port), "dbname": db, "user": user, "password": pwd}


def _connect():
    import psycopg2

    conn = psycopg2.connect(**_db_kwargs())
    conn.autocommit = False
    return conn


# ── Vision payload ───────────────────────────────────────────────────────────

_PIL_MIME = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}


def build_vision_content(record: dict) -> list[dict[str, Any]] | None:
    """Build multimodal content from in-DB image bytes + text context.

    Returns None when the image is missing / oversized / undecodable so the
    caller can flag the row instead of sending a text-only request (these
    figures are the whole point — a caption without the image is worthless).
    """
    img = record.get("image_data")
    if img is None:
        return None
    img = bytes(img)  # memoryview -> bytes
    if len(img) > MAX_IMAGE_BYTES:
        return None
    try:
        from PIL import Image

        fmt = Image.open(io.BytesIO(img)).format  # validates decodability
    except Exception:
        return None
    mime = _PIL_MIME.get(fmt or "", "image/jpeg")
    b64 = base64.b64encode(img).decode()

    text_parts = [
        f"Heading path: {record.get('heading_path') or ''}",
        f"Existing caption: {record.get('caption') or '(none)'}",
    ]
    return [
        {"type": "text", "text": "\n".join(text_parts)},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
    ]


async def label_one(client: httpx.AsyncClient, record: dict):
    content = build_vision_content(record)
    if content is None:
        return {"id": record["id"], "_skipped": True}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.post(
                OPENROUTER,
                json={
                    "model": LABEL_MODEL,
                    "messages": [
                        {"role": "system", "content": LABEL_PROMPT},
                        {"role": "user", "content": content},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 600,
                    "response_format": {"type": "json_object"},
                },
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=45.0,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            p = json.loads(raw)
            anatomy = p.get("anatomy", []) or []
            return {
                "id": record["id"],
                "caption_vlm": p.get("caption_summary", "") or "",
                "vlm_modality": p.get("modality", "") or "",
                "vlm_anatomy": ", ".join(anatomy)[:500],
                "vlm_pathology": (p.get("pathology", "") or "")[:500],
                "vlm_procedure": (p.get("procedure", "") or "")[:500],
                "vlm_keywords": json.dumps(p.get("keywords", []) or []),
                "is_neurosurgical": bool(p.get("is_neurosurgical", False)),
                "surgical_usefulness": int(p.get("surgical_usefulness", 0) or 0),
                "vlm_model": LABEL_MODEL,
            }
        except Exception as exc:
            if attempt == MAX_RETRIES:
                print(f"    [ERR] id={record['id']}: {type(exc).__name__}: {exc}", flush=True)
                return None
            await asyncio.sleep(attempt * 2.0)
    return None


# ── Persistence ──────────────────────────────────────────────────────────────

_UPDATE_SQL = """
    UPDATE textbook_figures SET
        caption_vlm          = %(caption_vlm)s,
        vlm_modality         = %(vlm_modality)s,
        vlm_anatomy          = %(vlm_anatomy)s,
        vlm_pathology        = %(vlm_pathology)s,
        vlm_procedure        = %(vlm_procedure)s,
        vlm_keywords         = %(vlm_keywords)s,
        is_neurosurgical     = %(is_neurosurgical)s,
        surgical_usefulness  = %(surgical_usefulness)s,
        vlm_model            = %(vlm_model)s,
        anatomical_region    = COALESCE(NULLIF(anatomical_region, ''), LEFT(NULLIF(%(vlm_anatomy)s, ''), 64)),
        procedure_approach   = COALESCE(NULLIF(procedure_approach, ''), LEFT(NULLIF(%(vlm_procedure)s, ''), 64)),
        figure_type          = COALESCE(NULLIF(figure_type, ''), LEFT(NULLIF(%(vlm_modality)s, ''), 32))
    WHERE id = %(id)s
"""

_SKIP_SQL = "UPDATE textbook_figures SET vlm_model = %s WHERE id = %s"
_SKIP_SENTINEL = LABEL_MODEL + ":skipped(no-usable-image)"


def store(conn, result: dict) -> str:
    cur = conn.cursor()
    if result.get("_skipped"):
        cur.execute(_SKIP_SQL, (_SKIP_SENTINEL, result["id"]))
        conn.commit()
        return "skipped"
    cur.execute(_UPDATE_SQL, result)
    conn.commit()
    return "ok"


def fetch_batch(conn, size: int):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, caption, heading_path, image_data
        FROM textbook_figures
        WHERE vlm_model IS NULL
        ORDER BY id
        LIMIT %s
        """,
        (size,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def count_remaining(conn) -> int:
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM textbook_figures WHERE vlm_model IS NULL")
    return cur.fetchone()[0]


# ── Orchestration ────────────────────────────────────────────────────────────


async def run(limit):
    conn = _connect()
    remaining = count_remaining(conn)
    target = remaining if limit is None else min(limit, remaining)
    print(f"  Captioning {target} figures via {LABEL_MODEL} (concurrency={CONCURRENCY})...")
    done = errors = skipped = 0

    async with httpx.AsyncClient(
        headers={"User-Agent": "CasePrep/1.0 (textbook figure labeler)"},
        limits=httpx.Limits(max_connections=CONCURRENCY + 5),
    ) as client:
        while done + errors + skipped < target:
            batch = fetch_batch(conn, CONCURRENCY * 3)
            if not batch:
                break
            if limit is not None:
                batch = batch[: target - (done + errors + skipped)]
            for i in range(0, len(batch), CONCURRENCY):
                chunk = batch[i : i + CONCURRENCY]
                results = await asyncio.gather(*(label_one(client, r) for r in chunk))
                for rec, res in zip(chunk, results):
                    if res is None:
                        errors += 1
                    elif store(conn, res) == "skipped":
                        skipped += 1
                    else:
                        done += 1
                print(
                    f"    {done} captioned, {skipped} skipped, {errors} errors "
                    f"({done + skipped + errors}/{target})",
                    flush=True,
                )
                await asyncio.sleep(REQUEST_DELAY)
    conn.close()
    print(f"  Done: {done} captioned, {skipped} skipped (no usable image), {errors} errors")


def dry_run():
    conn = _connect()
    remaining = count_remaining(conn)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM textbook_figures")
    total = cur.fetchone()[0]
    conn.close()
    est = remaining * (1700 / 1e6 * 0.30 + 250 / 1e6 * 2.50)
    print("=" * 60)
    print("  Textbook Figure Labeler — Dry Run")
    print("=" * 60)
    print(f"  Model:       {LABEL_MODEL}")
    print(f"  Total rows:  {total}")
    print(f"  To caption:  {remaining}  (vlm_model IS NULL)")
    print(f"  Key present: {bool(OPENROUTER_API_KEY)}")
    print(f"  Est. cost:   ~${est:.2f}")
    print("=" * 60)


if __name__ == "__main__":
    if "--dry-run" in sys.argv:
        dry_run()
        sys.exit(0)
    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY not resolved (env / PAPERS .env / ~/.hermes/.env).")
        sys.exit(1)
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    asyncio.run(run(limit))
