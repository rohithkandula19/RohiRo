"""health export parsing. pure parts only, no postgres."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from api.integrations.health_import import parse_apple_date, parse_records

FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_US">
 <ExportDate value="2026-08-16 09:00:00 -0700"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone" unit="count"
         startDate="2026-08-15 08:00:00 -0700" endDate="2026-08-15 08:10:00 -0700"
         value="412"/>
 <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Watch" unit="count/min"
         startDate="2026-08-15 08:05:00 -0700" value="61"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch"
         startDate="2026-08-14 23:10:00 -0700" endDate="2026-08-15 06:40:00 -0700"
         value="HKCategoryValueSleepAnalysisAsleepDeep"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch"
         startDate="2026-08-14 22:00:00 -0700" endDate="2026-08-14 23:00:00 -0700"
         value="HKCategoryValueSleepAnalysisBrandNewStage"/>
 <Record type="HKQuantityTypeIdentifierFlightsClimbed" sourceName="iPhone" unit="count"
         startDate="2026-08-15 08:00:00 -0700" endDate="2026-08-15 08:10:00 -0700"
         value="3"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone" unit="count"
         startDate="not a date" endDate="also bad" value="99"/>
</HealthData>
"""


def _write_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "export.xml"
    path.write_text(FIXTURE)
    return path


def test_parse_filters_and_tolerates(tmp_path: Path) -> None:
    # flights climbed is off the allowlist, one record has a junk date,
    # and one sleep stage is unknown. all three drop silently.
    recs = list(parse_records(_write_fixture(tmp_path)))
    assert len(recs) == 3
    assert [r["kind"] for r in recs] == ["steps", "heart_rate", "sleep_analysis"]


def test_parsed_values_and_fields(tmp_path: Path) -> None:
    recs = {r["kind"]: r for r in parse_records(_write_fixture(tmp_path))}
    steps = recs["steps"]
    assert steps["value"] == 412.0
    assert steps["unit"] == "count"
    assert steps["source"] == "iPhone"
    assert (steps["end_at"] - steps["start_at"]) == timedelta(minutes=10)
    # heart rate record has no endDate; end_at falls back to start_at.
    hr = recs["heart_rate"]
    assert hr["value"] == 61.0
    assert hr["end_at"] == hr["start_at"]


def test_sleep_stage_maps_to_numeric(tmp_path: Path) -> None:
    recs = [r for r in parse_records(_write_fixture(tmp_path)) if r["kind"] == "sleep_analysis"]
    assert len(recs) == 1  # the unknown stage was skipped
    assert recs[0]["value"] == 1.0  # deep sleep counts as asleep


def test_parse_apple_date() -> None:
    dt = parse_apple_date("2026-08-15 08:00:00 -0700")
    assert dt is not None
    assert (dt.year, dt.month, dt.day, dt.hour) == (2026, 8, 15, 8)
    assert dt.utcoffset() == timedelta(hours=-7)


def test_parse_apple_date_junk() -> None:
    assert parse_apple_date("not a date") is None
    assert parse_apple_date("2026-08-15") is None
    assert parse_apple_date("") is None
    assert parse_apple_date(None) is None
