#!/usr/bin/env python3
"""
Parallel image labeling pipeline using DeepSeek V3.
One instance per API key. Each gets a disjoint set of clusters.

Usage:
    python3 label_pipeline.py --api-key KEY --api-type deepseek --clusters "cluster1,cluster2"
    python3 label_pipeline.py --api-key KEY --api-type openrouter --clusters "cluster1,cluster2"

Flags:
    --dry-run    Count images and estimate cost, don't label
    --test       Label only 5 images to verify the pipeline works
    --resume     Skip fig_ids already in the labels table
"""
import sqlite3, json, os, sys, time, re, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bank.db")

SYSTEM_PROMPT = """You are a medical image classifier for neurosurgery. Analyze figure captions from academic papers and output structured labels.

Output valid JSON with these fields:
- "modality": one of [MRI, CT, CT_angiography, MR_angiography, DSA/angiogram, X-ray, ultrasound, PET, PET/CT, SPECT, intraoperative_photo, intraoperative_microscope, endoscopy, fluoroscopy, pathology/histology, surgical_anatomy_diagram, molecular_biology, chart/graph, EEG, fMRI, patient_photo, other]
- "is_neurosurgical": boolean (true if directly relevant to neurosurgery, false otherwise)
- "surgical_usefulness": integer 0-5 (0=no surgical value, 1=minimal, 2=some reference, 3=moderately useful for teaching/planning, 4=high surgical relevance, 5=essential surgical reference)
- "anatomy": list of anatomical structures mentioned (empty list [] if none)
- "pathology": primary disease or pathology (empty string "" if none)
- "procedure": surgical procedure (empty string "" if none)
- "keywords": list of 3-8 relevant keywords [(most relevant first)]
- "caption_summary": one-sentence summary of what the figure shows

Return ONLY valid JSON. No markdown, no explanation, no code fences. Just the JSON object."""


def get_db():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=10000")
    return db


def get_unlabeled_fig_ids(clusters, limit=None):
    """Get (fig_id, caption) for unlabeled images in specified clusters."""
    db = get_db()
    cur = db.cursor()
    placeholders = ",".join("?" for _ in clusters)
    query = f"""
        SELECT fig_id, caption, cluster FROM images
        WHERE cluster IN ({placeholders})
        AND fig_id NOT IN (SELECT fig_id FROM labels)
        AND caption IS NOT NULL AND caption != ''
        ORDER BY fig_id
    """
    params = list(clusters)
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    cur.execute(query, params)
    rows = cur.fetchall()
    db.close()
    return rows


def call_api(api_key, api_type, prompt, model, retries=3):
    """Call DeepSeek V3 API via direct or OpenRouter endpoint."""
    import urllib.request
    
    if api_type == "deepseek":
        url = "https://api.deepseek.com/chat/completions"
        model_name = model or "deepseek-chat"
    elif api_type == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        model_name = model or "deepseek/deepseek-chat-v3-0324"
    else:
        raise ValueError(f"Unknown API type: {api_type}")

    payload = json.dumps({
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Caption: {prompt}"}
        ],
        "temperature": 0.1,
        "max_tokens": 300,
        "response_format": {"type": "json_object"}
    }).encode("utf-8")

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=payload, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }, method="POST")
            if api_type == "openrouter":
                req.add_header("HTTP-Referer", "https://caseprep.app")
                req.add_header("X-Title", "CasePrep Image Bank")

            resp = urllib.request.urlopen(req, timeout=30)
            resp_data = json.loads(resp.read())
            content = resp_data["choices"][0]["message"]["content"]
            usage = resp_data.get("usage", {})

            # Try to parse JSON from response
            # The model should return clean JSON, but handle edge cases
            content_str = content.strip()
            if content_str.startswith("```"):
                content_str = content_str.split("\n", 1)[-1]
                if "```" in content_str:
                    content_str = content_str.rsplit("```", 1)[0]
            if content_str.startswith("```json"):
                content_str = content_str[7:]
                if "```" in content_str:
                    content_str = content_str.rsplit("```", 1)[0]
            content_str = content_str.strip()

            result = json.loads(content_str)
            
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            
            return result, input_tokens, output_tokens

        except json.JSONDecodeError as e:
            if attempt < retries - 1:
                time.sleep(1 * (attempt + 1))
                continue
            return {"error": f"JSON parse error: {e}", "raw": content[:500]}, 0, 0
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:500]
            if attempt < retries - 1 and e.code in (429, 500, 502, 503):
                time.sleep(2 * (attempt + 1))
                continue
            return {"error": f"HTTP {e.code}: {body}"}, 0, 0
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1 * (attempt + 1))
                continue
            return {"error": str(e)}, 0, 0

    return {"error": "Max retries exceeded"}, 0, 0


def label_one_image(api_key, api_type, model, row):
    """Label a single image and return a label dict or None on error."""
    fig_id, caption, cluster = row
    
    result, input_tokens, output_tokens = call_api(api_key, api_type, caption, model)
    
    if "error" in result:
        return {"fig_id": fig_id, "error": result["error"]}
    
    # Normalize fields
    modality = result.get("modality", "other")
    is_neurosurgical = bool(result.get("is_neurosurgical", False))
    usefulness = result.get("surgical_usefulness", 0)
    if usefulness is None:
        usefulness = 0
    usefulness = int(usefulness)
    usefulness = max(0, min(5, usefulness))
    
    anatomy = result.get("anatomy", [])
    if not isinstance(anatomy, list):
        anatomy = [str(anatomy)] if anatomy else []
    
    pathology = result.get("pathology", "") or ""
    procedure = result.get("procedure", "") or ""
    
    keywords = result.get("keywords", [])
    if not isinstance(keywords, list):
        keywords = [str(keywords)] if keywords else []
    
    summary = result.get("caption_summary", "") or ""
    
    return {
        "fig_id": fig_id,
        "modality": modality,
        "is_neurosurgical": 1 if is_neurosurgical else 0,
        "surgical_usefulness": usefulness,
        "anatomy": json.dumps(anatomy),
        "pathology": pathology,
        "procedure": procedure,
        "caption_summary": summary,
        "keywords": json.dumps(keywords),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def write_labels(labels):
    """Batch insert labels into the database with retry on lock."""
    if not labels:
        return 0
    count = 0
    for attempt in range(3):
        try:
            db = get_db()
            cur = db.cursor()
            for lbl in labels:
                if "error" in lbl:
                    continue
                cur.execute("""
                    INSERT OR IGNORE INTO labels 
                    (fig_id, modality, surgical_usefulness, anatomy, pathology, procedure, 
                     caption_summary, keywords, is_neurosurgical, model, labeled_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    lbl["fig_id"], lbl["modality"], lbl["surgical_usefulness"],
                    lbl["anatomy"], lbl["pathology"], lbl["procedure"],
                    lbl["caption_summary"], lbl["keywords"], lbl["is_neurosurgical"],
                    f"deepseek/deepseek-v3", datetime.utcnow().isoformat()
                ))
                count += 1
            db.commit()
            db.close()
            break
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < 2:
                time.sleep(1)
                continue
            print(f"  DB error: {e}")
            break
    return count


def process_pipeline(api_key, api_type, model, cluster_list, workers=8, test=False, resume=False):
    """Main pipeline loop."""
    print(f"\nPipeline: {api_type} | Model: {model} | Clusters: {len(cluster_list)}")
    print(f"Workers: {workers} | Test mode: {test} | Resume: {resume}")
    
    # Get images to label
    limit = 5 if test else None
    rows = get_unlabeled_fig_ids(cluster_list, limit=limit)
    
    if not rows:
        print("  No unlabeled images found in these clusters.")
        return
    
    total = len(rows)
    print(f"  Images to label: {total:,}")
    
    # Estimate cost
    est_input_tokens = total * 200  # system + caption
    est_output_tokens = total * 50  # V3 is concise
    est_cost = (est_input_tokens * 0.09 + est_output_tokens * 0.36) / 1_000_000  # $/1K tokens
    print(f"  Est. input tokens: {est_input_tokens:,}")
    print(f"  Est. output tokens: {est_output_tokens:,}")
    print(f"  Est. cost: ${est_cost:.4f}")
    
    # Process
    completed = 0
    errors = 0
    total_input_tokens = 0
    total_output_tokens = 0
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for row in rows:
            future = executor.submit(label_one_image, api_key, api_type, model, row)
            futures[future] = row
        
        for future in as_completed(futures):
            row = futures[future]
            try:
                result = future.result()
                if "error" in result:
                    errors += 1
                    if test:
                        print(f"  ERROR {row[0]}: {result['error']}")
                else:
                    # Write immediately
                    written = write_labels([result])
                    completed += written
                    total_input_tokens += result.get("input_tokens", 0)
                    total_output_tokens += result.get("output_tokens", 0)
                    
                    if completed % 50 == 0 or test:
                        elapsed = time.time() - start_time
                        rate = completed / elapsed if elapsed > 0 else 0
                        print(f"  Progress: {completed}/{total} ({rate:.1f}/s) | Errors: {errors} | Elapsed: {elapsed:.0f}s")
            except Exception as e:
                errors += 1
                print(f"  Exception for {row[0]}: {e}")
    
    elapsed = time.time() - start_time
    rate = completed / elapsed if elapsed > 0 else 0
    print(f"\n  === Pipeline Complete ===")
    print(f"  Labeled: {completed}/{total}")
    print(f"  Errors: {errors}")
    print(f"  Time: {elapsed:.0f}s ({rate:.1f} images/s)")
    print(f"  Input tokens: {total_input_tokens:,}")
    print(f"  Output tokens: {total_output_tokens:,}")
    print(f"  Actual cost: ${(total_input_tokens * 0.09 + total_output_tokens * 0.36) / 1_000_000:.4f}")
    
    return completed, errors


def main():
    parser = argparse.ArgumentParser(description="Label images with DeepSeek V3")
    parser.add_argument("--api-key", required=True, help="API key")
    parser.add_argument("--api-type", required=True, choices=["deepseek", "openrouter"])
    parser.add_argument("--model", default=None, help="Model name override")
    parser.add_argument("--clusters", required=True, help="Comma-separated cluster names")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent workers")
    parser.add_argument("--test", action="store_true", help="Test mode (5 images)")
    parser.add_argument("--resume", action="store_true", help="Skip already-labeled fig_ids")
    args = parser.parse_args()
    
    clusters = [c.strip() for c in args.clusters.split(",")]
    
    process_pipeline(
        api_key=args.api_key,
        api_type=args.api_type,
        model=args.model,
        cluster_list=clusters,
        workers=args.workers,
        test=args.test,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
