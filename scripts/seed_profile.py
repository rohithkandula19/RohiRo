"""interactive profile setup.

writes a minimal profile.md into the profile table so ro has something
to work with. you can edit it later from the /memory page.
"""

from __future__ import annotations

import asyncio

import asyncpg
import keyring


async def main() -> None:
    url = keyring.get_password("ro", "postgres_url") or "postgresql://ro:ro_local_dev@localhost:5432/ro"
    conn = await asyncpg.connect(url)
    try:
        existing = await conn.fetchval("select body from profile where id = 1")
        if existing and existing.strip():
            print("profile already has content. edit from /memory or pass --force to overwrite.")
            return

        print("a few quick questions to seed your profile.\n")
        name = input("your name: ").strip() or "ro"
        role = input("role / title: ").strip()
        company = input("company: ").strip()
        location = input("location: ").strip()
        focus = input("what you're focused on right now: ").strip()
        tone = input("how you want ro to write (one line): ").strip() or "direct, warm, no fluff"

        body = f"""# profile

## who
- name: {name}
- role: {role}
- company: {company}
- location: {location}

## focus
{focus}

## voice
{tone}

## preferences
- meetings: prefer 25 or 50 minute, not 30 or 60.
- email: short. plain text. no walls.
- code: ship small, reversible changes. tests first when it's not exploration.
"""

        await conn.execute(
            "update profile set body = $1, updated_at = now() where id = 1",
            body,
        )
        print("\nprofile seeded. open /memory to edit any time.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
