#!/usr/bin/env python3
"""
CasePrep Image Bank — LLM Labeler

Uses GPT-4o-mini (via OpenRouter) to tag each image in the bank with:
  - modality          (MRI, CT, DSA, intraop photo, diagram, etc.)
  - surgical_usefulness (0-5)
  - anatomy           (list of anatomical structures)
  - pathology         (primary pathology shown)
  - procedure         (surgical procedure if identifiable)
  - keywords          (searchable clinical keywords)
  - caption_summary   (concise one-line summary)

Reads unlabeled rows from bank.db, calls OpenRouter, writes labels to
a new 'labels' table.  Idempotent — skips already-labeled fig_ids.

Usage:
    python -m caseprep.image_bank.labeler              # full run
    python -m caseprep.image_bank.labeler --dry-run     # count only
"""

from __future__ import annotations
import asyncio
import base64
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# ── Constants ──────────────────────────────────────────────────────────────────

BANK_DIR = Path(__file__).parent.resolve()
DB_PATH = BANK_DIR / "bank.db"
LABEL_MODEL = "openai/gpt-4o-mini"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
REQUEST_DELAY = 0.15   # ~6 req/sec (keep it reasonable)
MAX_RETRIES = 3
CONCURRENCY = 20  # parallel API calls (balance speed vs rate limits)

# ⚠️ The user's OpenRouter key — try env, then PAPERS .env, then Hermes .env
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").replace("\r", "")
if not OPENROUTER_API_KEY:
    for dotenv in [
        "/mnt/c/Users/Michael/Desktop/PAPERS/.env",
        os.path.expanduser("~/.hermes/.env"),
    ]:
        try:
            with open(dotenv) as f:
                for line in f:
                    line = line.strip().replace("\r", "")
                    if line.startswith("OPENROUTER_API_KEY="):
                        OPENROUTER_API_KEY = line.split("=", 1)[1]
                        break
        except OSError:
            pass

# ── Label schema ──────────────────────────────────────────────────────────────

LABEL_PROMPT = """You are a neurosurgical image labeling assistant building a searchable image bank for a neurosurgeon. Your job: classify images so only neurosurgically-relevant content surfaces, and noise gets filtered out.

Respond with ONLY a JSON object (no markdown, no explanation):

{
  "modality": "<one of: MRI, CT, DSA/angiogram, MR_angiography, CT_angiography, X-ray, ultrasound, intraoperative_photo, intraoperative_microscope, endoscopy, surgical_anatomy_diagram, pathology/histology, molecular_biology, chart/graph, table, patient_photo, other>",
  "is_neurosurgical": <boolean: true if this image would be useful to a practicing neurosurgeon or neurointerventionalist, false otherwise>,
  "surgical_usefulness": <integer 0-5>,
  "anatomy": ["<specific anatomical structure 1>", "<specific anatomical structure 2>", ...],
  "pathology": "<primary disease, pathology, or condition shown — be specific with medical terminology. Leave empty only if the image is purely anatomical/technical>",
  "procedure": "<surgical, endovascular, or interventional procedure this image depicts OR would inform. If the image is diagnostic (CT/MRI/DSA), name the procedure the imaging is used to plan. If the image is intraoperative, name the specific surgical approach. Leave empty only for truly non-surgical images>",
  "caption_summary": "<one clinical sentence describing what the image shows, suitable for a surgeon scanning search results>",
  "keywords": ["<specific clinical term>", "<procedure name>", "<anatomical region>", "<pathology term>", "<imaging sequence>"]
}

surgical_usefulness guide (0-5):
  0 = Not neurosurgical at all — molecular pathway diagram, animal behavior test, cell culture photo, demographic chart, quality-of-life survey results. These are NOT useful to a neurosurgeon. is_neurosurgical should be false.
  1 = Tangentially neurosurgical — background science that might inform clinical reasoning (e.g., pathophysiology diagram, drug mechanism schematic). is_neurosurgical can be true or false depending on directness.
  2 = Generic anatomical reference — labeled anatomy diagram, textbook-style illustration of structures. Useful for education, not for surgical planning. is_neurosurgical should be true.
  3 = Clinically adjacent — imaging or diagram that informs a surgical decision but is not itself a surgical image (e.g., flowcharts for treatment algorithms, anatomy variations relevant to approach selection). is_neurosurgical should be true.
  4 = Clinically relevant — diagnostic imaging (MRI/CT/DSA of a pathology), intraoperative photos, surgical access photos, pathology slides that guide surgical margins, post-op outcome imaging. A neurosurgeon would study this image before or during a case. is_neurosurgical MUST be true.
  5 = Essential for surgical planning — approach-specific surgical anatomy, intraoperative exposure showing critical structures, complication imaging that surgeons must see, step-by-step surgical technique photos, stereotactic targeting images. This is gold for a surgical image bank. is_neurosurgical MUST be true.

CRITICAL RULES:
- is_neurosurgical is the primary filter: if false, the image gets excluded from the surgeon's search results regardless of other fields. Be conservative — when in doubt, set it false.
- modality: never use "other" for a diagram, chart, graph, or illustration — pick the most specific category. "other" is ONLY for genuinely uncategorizable images. Prefer "surgical_anatomy_diagram" over "diagram/illustration" for approach-relevant anatomy.
- anatomy: ALWAYS list specific structures visible or discussed. Even for sparse captions, infer anatomy from what you see in the image (e.g., "temporal bone", "petrous apex", "internal auditory canal" rather than just "skull base"). For intraoperative photos, name the critical structures in the surgical field. For charts with no visible anatomy, use the anatomical region from the caption/title.
- procedure: NEVER leave this empty when is_neurosurgical=true. If the image doesn't show a procedure being performed, name the surgical or interventional procedure this image would inform. A diagnostic MRI of a vestibular schwannoma has procedure "retrosigmoid approach" or "translabyrinthine approach". A CT of an aneurysm has procedure "clipping" or "coiling". Think: "what would a surgeon do with this information?"
- keywords: use MeSH-style clinical vocabulary: procedure names, specific anatomical regions, imaging sequences (T1, T2, FLAIR, DWI, SWI, TOF), pathology terms with qualifiers. Avoid generic words like "imaging", "outcomes", "data", "results". Every keyword should be something a surgeon might type into a search box.
- Electrophysiology recordings (LFP, EEG, MER, SSEP, MEP) with stereotactic or DBS context: these ARE neurosurgical (su=3-4, is_neurosurgical=true). Single-cell patch clamp or animal electrophysiology without surgical context: these are NOT (su=0-1, is_neurosurgical=false).
- For multi-panel figures: if any panel contains a neurosurgical image (MRI, CT, intraoperative photo), score the whole figure by the most surgical panel. If all panels are charts/graphs/molecular data, treat as noise.
- When the caption is "see text" or minimal: rely on the image itself and the article title/cluster to infer content. Never penalize an intraoperative photo just because the caption is minimal."""


def init_labels_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS labels (
            fig_id              TEXT PRIMARY KEY,
            modality            TEXT,
            is_neurosurgical    INTEGER,  -- boolean: 0 or 1
            surgical_usefulness INTEGER,
            anatomy             TEXT,   -- JSON list
            pathology           TEXT,
            procedure           TEXT,
            caption_summary     TEXT,
            keywords            TEXT,   -- JSON list
            raw_response        TEXT,
            model               TEXT,
            labeled_at          TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def count_unlabeled(conn: sqlite3.Connection) -> int:
    row = conn.execute("""
        SELECT COUNT(*) FROM images i
        LEFT JOIN labels l ON i.fig_id = l.fig_id
        WHERE l.fig_id IS NULL
    """).fetchone()
    return row[0] if row else 0


def count_labeled(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM labels").fetchone()
    return row[0] if row else 0


def get_batch(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """Fetch unlabeled images with the most informative captions first."""
    rows = conn.execute("""
        SELECT i.fig_id, i.caption, i.title, i.journal, i.cluster, i.pmcid, i.local_path
        FROM images i
        LEFT JOIN labels l ON i.fig_id = l.fig_id
        WHERE l.fig_id IS NULL
        ORDER BY LENGTH(i.caption) DESC
        LIMIT ?
    """, (limit,)).fetchall()
    return [
        {
            "fig_id": r[0],
            "caption": r[1] or "",
            "title": r[2] or "",
            "journal": r[3] or "",
            "cluster": r[4] or "",
            "pmcid": r[5] or "",
            "local_path": r[6] or "",
        }
        for r in rows
    ]


def build_vision_content(record: dict) -> list[dict[str, Any]]:
    """Build multimodal content: text caption + image for vision model."""
    text_parts = [
        f"Title: {record['title']}",
        f"Caption: {record['caption']}",
        f"Journal: {record['journal']}",
        f"CasePrep Cluster: {record['cluster']}",
    ]
    content: list[dict[str, Any]] = [
        {"type": "text", "text": "\n".join(text_parts)},
    ]

    # Attach image if available on disk
    local_path = record.get("local_path", "")
    if local_path and Path(local_path).exists():
        try:
            sz = Path(local_path).stat().st_size
            if sz > 2_000_000:  # skip images > 2MB
                return content  # text-only
            with open(local_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            ext = Path(local_path).suffix.lower()
            mime = "image/png" if ext == ".png" else "image/jpeg"
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })
        except OSError:
            pass  # proceed with text-only

    return content


async def label_image(
    client: httpx.AsyncClient,
    record: dict,
) -> dict[str, Any] | None:
    """Send image + caption to GPT-4o-mini vision, get structured labels back."""
    if not OPENROUTER_API_KEY:
        print("    [WARN] No API key — skipping", flush=True)
        return None

    vision_content = build_vision_content(record)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.post(
                OPENROUTER,
                json={
                    "model": LABEL_MODEL,
                    "messages": [
                        {"role": "system", "content": LABEL_PROMPT},
                        {"role": "user", "content": vision_content},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"},
                },
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

            raw = data["choices"][0]["message"]["content"]
            parsed = json.loads(raw)

            return {
                "fig_id": record["fig_id"],
                "modality": parsed.get("modality", ""),
                "is_neurosurgical": 1 if parsed.get("is_neurosurgical", False) else 0,
                "surgical_usefulness": parsed.get("surgical_usefulness", 0),
                "anatomy": json.dumps(parsed.get("anatomy", [])),
                "pathology": parsed.get("pathology", ""),
                "procedure": parsed.get("procedure", ""),
                "caption_summary": parsed.get("caption_summary", record["caption"][:120]),
                "keywords": json.dumps(parsed.get("keywords", [])),
                "raw_response": raw[:500],
                "model": LABEL_MODEL,
            }

        except Exception as exc:
            if attempt == MAX_RETRIES:
                print(f"    [ERR] {record['fig_id']}: {type(exc).__name__}: {exc}", flush=True)
                return None
            await asyncio.sleep(attempt * 2.0)

    return None


def store_label(conn: sqlite3.Connection, label: dict) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO labels (
            fig_id, modality, is_neurosurgical, surgical_usefulness, anatomy, pathology,
            procedure, caption_summary, keywords, raw_response, model
        ) VALUES (
            :fig_id, :modality, :is_neurosurgical, :surgical_usefulness, :anatomy, :pathology,
            :procedure, :caption_summary, :keywords, :raw_response, :model
        )
    """, label)
    conn.commit()


# ── Orchestration ───────────────────────────────────────────────────────────────


async def run_labeler(conn: sqlite3.Connection) -> None:
    """Label all unlabeled images in the bank."""
    total_unlabeled = count_unlabeled(conn)
    if total_unlabeled == 0:
        print("  No unlabeled images found.")
        return

    print(f"  Labeling {total_unlabeled} images via {LABEL_MODEL} (concurrency={CONCURRENCY})...")
    labeled = 0
    errors = 0

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(45.0),
        headers={"User-Agent": "CasePrep/1.0 (image labeler)"},
        limits=httpx.Limits(max_connections=CONCURRENCY + 5),
    ) as client:

        while True:
            batch = get_batch(conn, CONCURRENCY * 5)  # fetch 50 at a time
            if not batch:
                break

            # Process in chunks of CONCURRENCY
            for i in range(0, len(batch), CONCURRENCY):
                chunk = batch[i:i+CONCURRENCY]
                tasks = [label_image(client, record) for record in chunk]
                results = await asyncio.gather(*tasks)

                for record, result in zip(chunk, results):
                    if result:
                        store_label(conn, result)
                        labeled += 1
                    else:
                        errors += 1
                        conn.execute(
                            "INSERT OR IGNORE INTO labels (fig_id, model) VALUES (?, ?)",
                            (record["fig_id"], LABEL_MODEL),
                        )
                        conn.commit()

                if labeled % 100 == 0:
                    pct = labeled / total_unlabeled * 100
                    print(f"    {labeled}/{total_unlabeled} ({pct:.1f}%) labeled — {errors} errors", flush=True)

                await asyncio.sleep(REQUEST_DELAY)

    print(f"  Done: {labeled} labeled, {errors} errors")


def print_summary(conn: sqlite3.Connection) -> None:
    """Print a summary of the label distribution."""
    total = count_labeled(conn)

    # Modality breakdown
    modalities = conn.execute("""
        SELECT modality, COUNT(*) FROM labels
        WHERE modality != '' GROUP BY modality ORDER BY COUNT(*) DESC
    """).fetchall()

    # Surgical usefulness distribution
    usefulness = conn.execute("""
        SELECT surgical_usefulness, COUNT(*) FROM labels
        GROUP BY surgical_usefulness ORDER BY surgical_usefulness
    """).fetchall()

    # Top keywords
    keywords_raw = conn.execute("""
        SELECT keywords FROM labels WHERE keywords != '[]' AND keywords != ''
        LIMIT 500
    """).fetchall()

    # Count high-value images
    high_value = conn.execute("""
        SELECT COUNT(*) FROM labels WHERE surgical_usefulness >= 4
    """).fetchone()[0]

    print(f"\n{'='*60}")
    print(f"  Label Summary — {total} images labeled")
    print(f"{'='*60}")
    print(f"  Modality breakdown:")
    for mod, cnt in modalities[:10]:
        bar = "█" * max(1, int(cnt / max(1, modalities[0][1]) * 30))
        print(f"    {mod:30s} {cnt:4d} {bar}")
    print()
    print(f"  Surgical usefulness:")
    for score, cnt in usefulness:
        bar = "█" * max(1, int(cnt / max(1, max(u[1] for u in usefulness)) * 30))
        print(f"    {score}: {cnt:4d} {bar}")
    print(f"    → {high_value} images scored 4+ (clinically relevant)")
    print()
    print(f"  Top keywords:")
    kws: dict[str, int] = {}
    for (kw_json,) in keywords_raw:
        try:
            for kw in json.loads(kw_json):
                kws[kw.lower().strip()] = kws.get(kw.lower().strip(), 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass
    for kw, cnt in sorted(kws.items(), key=lambda x: -x[1])[:20]:
        print(f"    {kw:40s} {cnt}")
    print(f"{'='*60}\n")


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY not set.")
        print("Export it from ~/.hermes/.env or set it in your environment.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    init_labels_table(conn)

    if "--dry-run" in sys.argv:
        total = count_unlabeled(conn)
        labeled = count_labeled(conn)
        print(f"{'='*60}")
        print(f"  Image Bank Labeler — Dry Run")
        print(f"{'='*60}")
        print(f"  Model:        {LABEL_MODEL}")
        print(f"  DB:           {DB_PATH}")
        print(f"  Already labeled: {labeled}")
        print(f"  To label:     {total}")
        print(f"  Est. cost:    ~${total * 0.00015:.2f} (${1000 * 0.00015:.2f}/1K images)")
        print(f"  Est. time:    ~{total * 0.2 / 60:.0f} min at {REQUEST_DELAY}s/call")
        print(f"{'='*60}")
        conn.close()
        sys.exit(0)

    asyncio.run(run_labeler(conn))
    print_summary(conn)
    conn.close()
