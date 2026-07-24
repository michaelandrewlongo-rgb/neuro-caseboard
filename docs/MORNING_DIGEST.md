# Morning Rounds digest

An overnight PubMed watch that emails you cited bullets at **05:30 America/Chicago**.
You register topics once; the box checks them every night and mails only what's new.

## Why it runs where it does

It runs on the Hetzner **host**, not inside the `caseboard` container, and it is
deliberately **stdlib-only** (no venv, no `pip install`, no image rebuild, no container
restart). The box has 2 cores and ~3.8 GB RAM with the container already resident, so the
digest is built to be incapable of disturbing it: a live 8-topic run costs
**0.4 s of CPU** — everything else is waiting on PubMed and OpenRouter.

That choice has one cost: it does not reuse `neuro_caseboard/literature/`, so it gets no
textbook grounding, no entailment gate, and no telemetry row. Add those by moving it into
the container image when the digest needs to cite the corpus, not before.

## Files on the box

| Path | What it is |
|---|---|
| `/opt/caseboard/morning_digest.py` | the script (source of truth: `scripts/morning_digest.py`) |
| `/opt/caseboard/digest_topics.txt` | your watch list — **edit this** |
| `/opt/caseboard/digest.env` | mail credential, `chmod 600` |
| `/opt/caseboard/digest.db` | PMIDs already emailed, so nothing repeats |
| `/opt/caseboard/run_digest.sh` | cron entrypoint; sources `.env` + `digest.env` |
| `/var/log/caseboard-digest.log` | every run appends here |

## Editing your topics

One PubMed query per line. `Label :: query` gives the section a friendlier heading.
Blank lines and `#` comments are ignored.

```
Vasospasm / DCI :: ("subarachnoid hemorrhage") AND (vasospasm OR "delayed cerebral ischemia")
chronic subdural hematoma
```

Nothing to restart — the next run picks up the file.

## Running it by hand

```bash
ssh hub
set -a; . /opt/caseboard/.env; . /opt/caseboard/digest.env; set +a
cd /opt/caseboard

python3 morning_digest.py --dry-run --out /tmp/digest.html   # build, don't send, don't mark seen
python3 morning_digest.py                                    # build and email
```

## The two design rules worth keeping

**Papers are marked "seen" only after the SMTP server accepts the message.** A failed send
therefore re-reports tomorrow rather than silently swallowing a day of literature. The
ordering is enforced by `test_a_failed_send_does_not_swallow_the_papers`.

**A quiet day still sends an email.** Silence is indistinguishable from a dead cron, so
"nothing new" arrives as a one-line message. That is the liveness signal — if no mail
arrives at all, the job itself is broken, so check the log.

## Recency window

`--days 7` with the seen-database, rather than a tight 1-day window: PubMed backfills entry
dates, so a narrow window drops papers permanently, while the dedup table means a wide one
costs you nothing but a slightly longer first run. The window is on `[EDAT]` (entry date),
not `[PDAT]` — a 2024 paper indexed last night is still new to you.

## Gotchas

- Port **465 is blocked** outbound on this box; 587 STARTTLS works. Don't switch to SMTPS.
- Gmail needs an **app password**, not your account password (requires 2-step verification).
- Papers with no abstract are skipped (nothing citable) but still marked seen, so they
  aren't re-fetched nightly forever.
- Per-topic cap is 6 (`--max-per-topic`). Anything dropped is reported in the email and the
  log — the digest never truncates silently.
- The log is never rotated. It grows ~2 KB/day; add logrotate if that ever matters.
