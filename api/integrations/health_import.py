"""body ledger ingestion. apple health export -> health_samples.

the health app exports export.zip with export.xml inside. that file runs
to hundreds of megabytes of <Record> elements, so parsing streams with
iterparse and clears elements as it goes. only a small allowlist of
record types is kept; everything else is skipped. inserts dedupe on
(kind, start_at, value) so re-imports are cheap.

run by hand: python -m api.integrations.health_import --file export.zip
"""

from __future__ import annotations

import argparse
import tempfile
import zipfile
from collections import Counter
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree

from api.memory.db import db
from api.observability.logging import log

APPLE_DATE = "%Y-%m-%d %H:%M:%S %z"

# hk identifier -> short name in health_samples.kind
KINDS = {
    "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierHeartRate": "heart_rate",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_hr",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv",
    "HKCategoryTypeIdentifierSleepAnalysis": "sleep_analysis",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "active_energy",
    "HKQuantityTypeIdentifierAppleExerciseTime": "exercise_minutes",
    "HKQuantityTypeIdentifierBodyMass": "weight",
}

# sleep records carry a text stage in the value attr. keep a small
# numeric mapping: 0 in bed, 1 asleep (any depth), 2 awake. unknown
# stages are skipped rather than guessed.
SLEEP_STAGES = {
    "HKCategoryValueSleepAnalysisInBed": 0.0,
    "HKCategoryValueSleepAnalysisAsleep": 1.0,
    "HKCategoryValueSleepAnalysisAsleepUnspecified": 1.0,
    "HKCategoryValueSleepAnalysisAsleepCore": 1.0,
    "HKCategoryValueSleepAnalysisAsleepDeep": 1.0,
    "HKCategoryValueSleepAnalysisAsleepREM": 1.0,
    "HKCategoryValueSleepAnalysisAwake": 2.0,
}

BATCH = 1000


def parse_apple_date(raw: Optional[str]) -> Optional[datetime]:
    """apple's export format, e.g. '2026-08-01 07:30:00 -0800'. none on junk."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), APPLE_DATE)
    except ValueError:
        return None


def _value_for(kind: str, raw: Optional[str]) -> Optional[float]:
    """numeric value for a record, or none when it should be skipped."""
    if kind == "sleep_analysis":
        return SLEEP_STAGES.get(raw or "")
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _record(elem: ElementTree.Element) -> Optional[dict[str, Any]]:
    """one <Record> element -> a sample dict, or none if filtered out."""
    kind = KINDS.get(elem.get("type") or "")
    if kind is None:
        return None
    start_at = parse_apple_date(elem.get("startDate"))
    if start_at is None:
        return None
    value = _value_for(kind, elem.get("value"))
    if value is None:
        return None
    return {
        "kind": kind,
        "value": value,
        "unit": elem.get("unit") or "",
        "start_at": start_at,
        "end_at": parse_apple_date(elem.get("endDate")) or start_at,
        "source": elem.get("sourceName") or "",
    }


def parse_records(xml_path: str | Path) -> Iterator[dict[str, Any]]:
    """stream allowlisted records out of export.xml. bad rows are skipped.

    memory stays flat: each element is cleared once read, and the root is
    cleared so finished children do not accumulate.
    """
    context = ElementTree.iterparse(str(xml_path), events=("start", "end"))
    _, root = next(context)
    for event, elem in context:
        if event != "end":
            continue
        rec = _record(elem) if elem.tag == "Record" else None
        elem.clear()
        root.clear()
        if rec is not None:
            yield rec


async def _flush(batch: list[dict[str, Any]], inserted: Counter[str]) -> None:
    rows = await db.fetch(
        """insert into health_samples (kind, value, unit, start_at, end_at, source)
           select * from unnest($1::text[], $2::float8[], $3::text[],
                                $4::timestamptz[], $5::timestamptz[], $6::text[])
           on conflict (kind, start_at, value) do nothing
           returning kind""",
        [r["kind"] for r in batch],
        [r["value"] for r in batch],
        [r["unit"] for r in batch],
        [r["start_at"] for r in batch],
        [r["end_at"] for r in batch],
        [r["source"] for r in batch],
    )
    for row in rows:
        inserted[row["kind"]] += 1


async def _ingest(xml_path: Path, inserted: Counter[str]) -> int:
    seen = 0
    batch: list[dict[str, Any]] = []
    for rec in parse_records(xml_path):
        seen += 1
        batch.append(rec)
        if len(batch) >= BATCH:
            await _flush(batch, inserted)
            batch = []
    if batch:
        await _flush(batch, inserted)
    return seen


async def import_export(path: str | Path) -> dict[str, Any]:
    """import a health export (.zip or bare .xml) into health_samples.

    returns {"seen": n, "inserted": {kind: n}}. seen counts allowlisted
    records parsed; inserted counts new rows after dedupe.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    inserted: Counter[str] = Counter()
    if p.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(p) as zf:
            name = next((n for n in zf.namelist() if n.endswith("export.xml")), None)
            if name is None:
                raise ValueError(f"no export.xml inside {p.name}")
            seen = await _ingest(Path(zf.extract(name, tmp)), inserted)
    else:
        seen = await _ingest(p, inserted)

    log.info(
        "health import done",
        path=str(p), seen=seen, inserted=sum(inserted.values()),
    )
    return {"seen": seen, "inserted": dict(inserted)}


async def weekly_summary() -> dict[str, Any]:
    """per-kind avg and sum over the last seven days of samples."""
    rows = await db.fetch(
        """select kind, avg(value) as avg, sum(value) as sum, count(*) as samples
           from health_samples
           where start_at > now() - interval '7 days'
           group by kind order by kind"""
    )
    return {
        r["kind"]: {
            "avg": round(float(r["avg"]), 2),
            "sum": round(float(r["sum"]), 2),
            "samples": int(r["samples"]),
        }
        for r in rows
    }


if __name__ == "__main__":
    import asyncio

    parser = argparse.ArgumentParser(description="import an apple health export")
    parser.add_argument("--file", required=True, help="path to export.zip or export.xml")
    args = parser.parse_args()
    print(asyncio.run(import_export(args.file)))
