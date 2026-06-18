#!/usr/bin/env python3
"""
Caption-based pre-filter to remove extraneous non-surgical images.
Dry-run mode shows what would be deleted; --execute actually removes.
"""
import sqlite3, sys, re
from pathlib import Path

DB = Path.home() / "projects/caseprep/caseprep/image_bank/bank.db"

# Patterns that strongly indicate non-surgical molecular biology / chart images
NOISE_PATTERNS = [
    # Molecular biology markers
    r"western\s*blot", r"immunofluorescen", r"immunohistochem",
    r"knockout", r"knock-in", r"knock\s*in", r"transfect",
    r"HEK293", r"HeLa", r"HEK\s*293", r"lentivir", r"siRNA",
    r"qPCR", r"RT-PCR", r"RT\s*PCR", r"ELISA",
    r"co-immunoprecipit", r"immunoprecipit",
    r"confocal\s*microscop", r"flow\s*cytometr",
    r"SDS-PAGE", r"sodium\s*dodecyl", r"polyacrylamide",
    r"plasmid", r"vector\s*construct",

    # Cell biology / in-vitro
    r"cell\s*culture", r"cell\s*line", r"in\s*vitro",
    r"fibroblast", r"astrocyte\s*culture", r"neuron\s*culture",
    r"iPSC", r"induced\s*pluripotent",
    r"differentiation\s*assay", r"proliferation\s*assay",

    # Mouse/rat behavior (non-surgical)
    r"C57BL", r"wild.type\s*mice", r"wild-type\s*mice",
    r"open\s*field\s*test", r"elevated\s*plus\s*maze",
    r"morris\s*water\s*maze", r"von\s*Frey",
    r"mouse\s*model", r"rat\s*model", r"rodent\s*model",

    # Generic chart/statistics only (when caption is purely about stats)
    r"error\s*bars?\s*(represent|indicate|show|denote)\s*(mean|SD|SEM|standard)",
    r"p\s*<\s*0[.]\d+.*(Student|Mann|ANOVA|Kruskal|Wilcoxon|Fisher|chi.square)",
    r"n\s*=\s*\d+.*(biological|independent|technical).*replicate",
    r"box\s*plot.*median.*interquartile", r"violin\s*plot",
    r"scatter\s*plot.*each\s*dot\s*represents",
    r"bar\s*(chart|graph).*(mean|average).*(SEM|SD|error)",
    r"Kaplan.Meier.*(survival|curve)", r"hazard\s*ratio.*95%",
    r"forest\s*plot", r"funnel\s*plot", r"Bland.Altman",

    # Purely molecular/genetic
    r"gene\s*expression.*(heat\s*map|volcano\s*plot|PCA\s*plot)",
    r"RNA-seq", r"RNA\s*sequencing", r"single.cell\s*RNA",
    r"transcriptom", r"proteom", r"metabolom",
    r"protein\s*expression.*quantif", r"mRNA\s*level",
    r"phosphorylation", r"ubiquitin", r"acetylation",

    # Quality-of-life / surveys
    r"(quality.of.life|QoL|SF-36|EQ-5D|NIHSS|mRS|GOS).*score",
    r"(patient.reported|self.reported).*outcome",
    r"questionnaire", r"survey\s*response",
    r"consort\s*diagram", r"flow\s*chart.*(enrollment|screening|eligibility)",
    r"PRISMA\s*flow", r"study\s*flow\s*diagram",
]

def load_db():
    return sqlite3.connect(str(DB))

def is_noise_caption(caption: str, title: str) -> bool:
    """Check if caption or title matches noise patterns."""
    text = (caption + " " + title).lower()
    for pat in NOISE_PATTERNS:
        if re.search(pat, text):
            return True
    return False

def analyze(dry_run=True):
    conn = load_db()
    conn.execute("PRAGMA busy_timeout=10000")

    clusters = [r[0] for r in conn.execute(
        "SELECT DISTINCT cluster FROM images ORDER BY cluster"
    ).fetchall()]

    total_images = 0
    total_noise = 0
    results = []

    for cluster in clusters:
        rows = conn.execute(
            "SELECT fig_id, caption, title, local_path FROM images WHERE cluster=?",
            (cluster,)
        ).fetchall()

        cluster_total = len(rows)
        cluster_noise_ids = []
        cluster_noise_paths = []

        for fig_id, caption, title, local_path in rows:
            if is_noise_caption(caption or "", title or ""):
                cluster_noise_ids.append(fig_id)
                cluster_noise_paths.append(local_path)

        cluster_noise = len(cluster_noise_ids)
        total_images += cluster_total
        total_noise += cluster_noise

        pct = cluster_noise / cluster_total * 100 if cluster_total else 0
        remaining = cluster_total - cluster_noise
        results.append((cluster, cluster_total, cluster_noise, remaining, pct))

        if dry_run:
            print(f"  {cluster:42s} {cluster_total:5d} → -{cluster_noise:4d} = {remaining:4d} ({pct:3.0f}% noise)")
        else:
            # Actually delete
            if cluster_noise_ids:
                conn.executemany(
                    "DELETE FROM images WHERE fig_id=?",
                    [(fid,) for fid in cluster_noise_ids]
                )
                conn.executemany(
                    "DELETE FROM labels WHERE fig_id=?",
                    [(fid,) for fid in cluster_noise_ids]
                )
            # Delete files
            for p in cluster_noise_paths:
                if p and Path(p).exists():
                    try:
                        Path(p).unlink()
                    except OSError:
                        pass
            print(f"  {cluster:42s} removed {cluster_noise}, {remaining} remain")

    conn.commit()

    print(f"\n{'='*60}")
    if dry_run:
        print(f"  DRY RUN — no deletions made")
    else:
        print(f"  EXECUTED — deletions committed")
    print(f"  Total images:    {total_images}")
    print(f"  Noise to remove: {total_noise} ({total_noise/total_images*100:.0f}%)")
    print(f"  Would keep:      {total_images - total_noise}")
    print(f"{'='*60}")

    conn.close()
    return total_noise

if __name__ == "__main__":
    dry_run = "--execute" not in sys.argv
    if dry_run:
        print("CAPTION-BASED NOISE SCAN (dry run)\n")
    else:
        print("⚠️  EXECUTING DELETIONS ⚠️\n")
    analyze(dry_run=dry_run)
