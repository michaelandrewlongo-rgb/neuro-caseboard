from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TS_FILE = REPO / "web" / "src" / "lib" / "briefingTypes.ts"


def test_generated_ts_matches_checked_in_file():
    """The checked-in TS types must equal a fresh generation from the Pydantic schema.
    If this fails, run: python3 scripts/gen_briefing_types.py  (regenerates the file)."""
    from scripts.gen_briefing_types import generate_ts
    assert TS_FILE.read_text() == generate_ts(), (
        "briefingTypes.ts is stale — run `python3 scripts/gen_briefing_types.py`")


def test_generated_ts_has_core_interfaces():
    from scripts.gen_briefing_types import generate_ts
    ts = generate_ts()
    for name in ("OperativeBriefing", "BriefingItem", "BriefingFigure",
                 "BriefingReference", "BriefingProvenance", "DecisionAlgorithm"):
        assert f"export interface {name}" in ts
    # discriminated equipment union collapses to a named union type
    assert "export type EquipmentPlan =" in ts
    # Optional → `| null`; enum → string-literal union
    assert "DecisionAlgorithm | null" in ts
    assert '"critical" | "high" | "optional"' in ts
