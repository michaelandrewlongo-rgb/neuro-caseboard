#!/usr/bin/env python3
"""Batch-run 48 nsgy questions against neuro-caseboard /api/ask"""
import re, json, subprocess, time, sys

with open('/mnt/c/Users/Michael/Downloads/contemporary-qs-in-neurosurgery') as f:
    text = f.read()

questions = []
current_section = None
lines = text.split('\n')
i = 0
while i < len(lines):
    line = lines[i]
    if line.startswith('#'):
        current_section = line.lstrip('#').strip()
        i += 1
        continue
    m = re.match(r'^(\d+)\.\s+(.*)', line)
    if m:
        num, qtext = m.group(1), m.group(2)
        while i+1 < len(lines) and lines[i+1].strip() and not re.match(r'^\d+\.\s', lines[i+1]) and not lines[i+1].startswith('#'):
            i += 1
            qtext += ' ' + lines[i].strip()
        questions.append((current_section, num, qtext))
    i += 1

print(f"Running {len(questions)} questions...\n")

outpath = '/mnt/c/Users/Michael/Downloads/nsgy-results.txt'
with open(outpath, 'w') as out:
    for idx, (section, num, q) in enumerate(questions, 1):
        label = f"[{idx}/{len(questions)}] {section} Q{num}"
        print(f"{label}: {q[:100]}...")
        try:
            r = subprocess.run([
                'curl', '-s', '--max-time', '300',
                '-X', 'POST', 'http://127.0.0.1:8001/api/ask',
                '-H', 'Content-Type: application/json',
                '-d', json.dumps({"question": q, "force": True})
            ], capture_output=True, text=True, timeout=310)
            out.write(f"\n{'='*80}\n{label}\n{'='*80}\nQ: {q}\n\n{r.stdout}\n")
            out.flush()
        except Exception as e:
            out.write(f"\n{'='*80}\n{label}\n{'='*80}\nQ: {q}\n\nERROR: {e}\n")
            out.flush()
            print(f"  ERROR: {e}")
        time.sleep(1)  # don't hammer the server

print(f"\nDone: {outpath}")
