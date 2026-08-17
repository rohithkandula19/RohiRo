"""skills bridge: frontmatter parsing and catalog scanning."""

from __future__ import annotations

import asyncio
from unittest.mock import patch


def test_frontmatter_parsing() -> None:
    from api.skills_bridge import _parse_frontmatter

    text = "---\nname: reviewer\ndescription: reviews things well\nversion: 1.0\nallowed-tools:\n  - Bash\n---\n# body"
    meta = _parse_frontmatter(text)
    assert meta["name"] == "reviewer"
    assert meta["description"] == "reviews things well"
    assert "allowed-tools" not in meta


def test_no_frontmatter_is_empty() -> None:
    from api.skills_bridge import _parse_frontmatter

    assert _parse_frontmatter("# just markdown") == {}


def test_catalog_scans_two_levels(tmp_path) -> None:
    from api import skills_bridge as sb

    (tmp_path / "solo").mkdir()
    (tmp_path / "solo" / "SKILL.md").write_text("---\nname: solo\ndescription: top level\n---\nbody")
    (tmp_path / "pack" / "inner").mkdir(parents=True)
    (tmp_path / "pack" / "inner" / "SKILL.md").write_text("---\nname: inner\ndescription: nested\n---\nbody")
    (tmp_path / "noise").mkdir()
    (tmp_path / "noise" / "README.md").write_text("not a skill")

    with patch.object(sb, "DEFAULT_PATHS", [tmp_path]), \
         patch.object(sb, "_catalog_cache", (0.0, [])), \
         patch.object(sb, "_search_paths", new=_fake_paths(tmp_path)):
        found = asyncio.run(sb.catalog(limit=100))
    names = {s["name"] for s in found}
    assert names == {"solo", "pack/inner"}


def _fake_paths(tmp_path):
    async def _paths():
        return [tmp_path]
    return _paths
