#!/usr/bin/env python3
import os, sys, asyncio, httpx

# Load key
for dp in ["/mnt/c/Users/Michael/Desktop/PAPERS/.env", os.path.expanduser("~/.hermes/.env")]:
    try:
        for line in open(dp):
            line = line.strip().replace("\r", "")
            eq = line.find("=")
            if eq > 0 and line[:eq] == "OPENROUTER_API_KEY":
                os.environ["OPENROUTER_API_KEY"] = line[eq+1:]
    except OSError:
        pass

from caseprep.image_bank import labeler
import sqlite3

print(f"Key: {len(labeler.OPENROUTER_API_KEY)} chars")
print(f"Model: {labeler.LABEL_MODEL}")

conn = sqlite3.connect(str(labeler.DB_PATH))
conn.execute("PRAGMA busy_timeout=10000")
labeler.init_labels_table(conn)

row = conn.execute("""
    SELECT i.fig_id, i.caption, i.title, i.journal, i.cluster, i.pmcid, i.local_path
    FROM images i LEFT JOIN labels l ON i.fig_id = l.fig_id
    WHERE l.fig_id IS NULL AND i.local_path != ''
    ORDER BY RANDOM() LIMIT 1
""").fetchone()
conn.close()

record = {"fig_id": row[0], "caption": row[1] or "", "title": row[2] or "",
          "journal": row[3] or "", "cluster": row[4] or "", "pmcid": row[5] or "",
          "local_path": row[6] or ""}
print(f"Image: {record['fig_id']} ({record['cluster']})")

async def test():
    async with httpx.AsyncClient(timeout=httpx.Timeout(45.0)) as c:
        r = await labeler.label_image(c, record)
        if r is None:
            print("RESULT: None")
        else:
            print(f"OK: su={r['surgical_usefulness']} neuro={r['is_neurosurgical']} mod={r['modality']}")

asyncio.run(test())
