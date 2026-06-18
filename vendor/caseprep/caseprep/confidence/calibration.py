
"""Calibration data collection for confidence scoring.

Logs every (predicted_confidence, actual_outcome) pair for future
isotonic regression calibration. Ground truth (actual_correct) is
filled later via manual review.
"""

from __future__ import annotations

import json
import datetime as dt
from pathlib import Path
from typing import Any


CALIBRATION_DIR = Path.home() / ".hermes" / "caseprep" / "calibration"
CALIBRATION_FILE = CALIBRATION_DIR / "calibration_log.jsonl"


def log_calibration_point(
    slot_name: str,
    predicted_confidence: float,
    predicted_entropy: float,
    actual_correct: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append a calibration data point to the log file.
    
    Args:
        slot_name: compiler slot being scored (e.g. "Neural Structures")
        predicted_confidence: normalized confidence score [0,1]
        predicted_entropy: Shannon entropy of the token distribution
        actual_correct: None until manually validated by clinician review
        metadata: extra context (procedure_family, topic, etc.)
    """
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    
    record = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "slot_name": slot_name,
        "predicted_confidence": predicted_confidence,
        "predicted_entropy": predicted_entropy,
        "actual_correct": actual_correct,
        "metadata": metadata or {},
    }
    
    with open(CALIBRATION_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")


def load_calibration_points() -> list[dict[str, Any]]:
    """Load all calibration points with known ground truth.
    
    Only returns points where actual_correct is not None — those have
    been validated by manual clinician review.
    """
    if not CALIBRATION_FILE.exists():
        return []
    points = []
    with open(CALIBRATION_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            pt = json.loads(line)
            if pt["actual_correct"] is not None:
                points.append(pt)
    return points
