"""life report, pure parts. render_markdown and the weekday histogram."""

from __future__ import annotations

from api.life_report import render_markdown, weekday_histogram

FULL = {
    "days": 30,
    "messages": [
        {"contact": "mom", "count": 42},
        {"contact": "sam@work.com", "count": 17},
    ],
    "loops": {"opened": 5, "closed": 7},
    "actions": {"approved": 12, "rejected": 1, "edited": 3},
    "spend": {
        "tokens": 123456,
        "calls": 89,
        "top_runs": [
            {"run_label": "digest", "tokens": 60000},
            {"run_label": "open-loops", "tokens": 40000},
        ],
    },
    "weekdays": {
        "monday": 10, "tuesday": 2, "wednesday": 0, "thursday": 4,
        "friday": 9, "saturday": 1, "sunday": 3,
    },
}


def test_render_full_report() -> None:
    md = render_markdown(FULL)
    assert md.startswith("# your month")
    assert "## people" in md
    assert "- mom: 42" in md
    assert "59 messages" in md  # 42 + 17
    assert "## loops" in md
    assert "closed 7" in md and "opened 5" in md
    assert "## actions" in md
    assert "12 approved, 1 rejected, 3 edited" in md
    assert "## spend" in md
    assert "123,456 tokens across 89 calls" in md
    assert "- digest: 60,000" in md
    assert "## rhythm" in md
    assert "monday was your loudest day." in md
    assert "quiet month" not in md


def test_render_empty_report_falls_back() -> None:
    md = render_markdown({})
    assert "(quiet month — not enough data yet)" in md
    assert "##" not in md


def test_render_partial_report_skips_empty_sections() -> None:
    md = render_markdown({"days": 30, "messages": [{"contact": "mom", "count": 3}]})
    assert "## people" in md
    assert "## loops" not in md
    assert "## actions" not in md
    assert "## spend" not in md
    assert "## rhythm" not in md
    assert "quiet month" not in md


def test_render_zero_counts_count_as_no_data() -> None:
    md = render_markdown({
        "loops": {"opened": 0, "closed": 0},
        "actions": {"approved": 0, "rejected": 0, "edited": 0},
        "spend": {"tokens": 0, "calls": 0, "top_runs": []},
    })
    assert "(quiet month — not enough data yet)" in md


def test_weekday_histogram_maps_postgres_dow() -> None:
    # postgres dow: 0 = sunday .. 6 = saturday
    hist = weekday_histogram([(0, 2), (1, 5), (6, 1)])
    assert hist["sunday"] == 2
    assert hist["monday"] == 5
    assert hist["saturday"] == 1
    assert hist["tuesday"] == 0
    assert list(hist) == [
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday",
    ]


def test_weekday_histogram_skips_junk() -> None:
    hist = weekday_histogram([("x", 1), (9, 4), (-1, 2), (2, "3"), (3, 0)])
    assert hist["tuesday"] == 3  # (2, "3") coerces cleanly
    assert sum(hist.values()) == 3


def test_weekday_histogram_empty_means_missing() -> None:
    assert weekday_histogram([]) == {}
    assert weekday_histogram([(1, 0), ("bad", "bad")]) == {}
