#!/usr/bin/env python3
"""Quick debug: why is the labeler failing on every image?"""
import asyncio, base64, json, os, sqlite3, sys
from pathlib import Path

env = os.environ.copy()
with open("/mnt/c/Users/Michael/Desktop/PAPERS/.env") as f:
    for line in f:
        line = line.strip().replace("\r", "")
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v
OR_KEY = env.get("OPENROUTER_API_KEY", "")
print(f"Key: {len(OR_KEY)} chars")

# Load the labeler prompt
from caseprep.image_bank import labeler
PROMPT = labeler.LABEL_PROMPT
MODEL = labeler.LABEL_MODEL
print(f"Model: {MODEL}")
print(f"Prompt length: {len(PROMPT)} chars")

# Get one image
db_path = Path.home() / "projects/caseprep/caseprep/image_bank/bank.db"
conn = sqlite3.connect(str(db_path))
conn.execute("PRAGMA busy_timeout=10000")
rows = conn.execute("""
    SELECT i.fig_id, i.caption, i.title, i.journal, i.cluster, i.pmcid, i.local_path
    FROM images i LEFT JOIN labels l ON i.fig_id = l.fig_id
    WHERE l.fig_id IS NULL AND i.local_path != '' ORDER BY LENGTH(i.caption) DESC LIMIT 1
""").fetchall()
conn.close()
if not rows:
    print("No unlabeled images!")
    sys.exit(1)

fig_id = rows[0][0]
caption = rows[0][1] or ""
title = rows[0][2] or ""
journal = rows[0][3] or ""
cluster = rows[0][4] or ""
local_path = rows[0][6] or ""

print(f"Image: {fig_id} ({cluster})")
print(f"Caption: {caption[:80]}...")
print(f"Title: {title[:80]}...")

with open(local_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode()
print(f"Base64: {len(b64)/1024:.0f} KB")

import httpx

async def test():
    content = [
        {"type": "text", "text": f"Title: {title}\nCaption: {caption}\nJournal: {journal}\nCasePrep Cluster: {cluster}"},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
    ]

    async with httpx.AsyncClient(timeout=httpx.Timeout(45.0)) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.1,
                "max_tokens": 500,
                "response_format": {"type": "json_object"},
            },
            headers={"Authorization": f"Bearer {OR_KEY}", "Content-Type": "application/json",
                     "HTTP-Referer": "https://caseprep.local"},
            timeout=45.0,
        )
        print(f"\nHTTP {resp.status_code}")
        data = resp.json()
        if resp.status_code != 200:
            err = data.get("error", {})
            print(f"Error: {json.dumps(err, indent=2)[:500]}")
            return
        raw = data["choices"][0]["message"]["content"]
        finish = data["choices"][0].get("finish_reason", "")
        usage = data.get("usage", {})
        print(f"Finish: {finish}")
        print(f"Tokens: {usage}")
        print(f"Raw ({len(raw)} chars):")
        print(raw[:500])

asyncio.run(test())
