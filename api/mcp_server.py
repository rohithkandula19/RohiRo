"""ro as an mcp server. your agent becomes personal infrastructure.

any mcp client — claude code, cursor, another agent — can connect to ro
and get: memory search, the lifetime archive, open loops, pending
approvals, playbook runs, and the ability to message you through your own
channels. ro stops being an app and becomes the layer your other tools
stand on.

wire into claude code (~/.claude.json or claude mcp add):

  {
    "mcpServers": {
      "ro": {
        "command": "uv",
        "args": ["run", "--project", "/Users/you/RohiRo", "python", "-m", "api.mcp_server"]
      }
    }
  }

boundaries, same as everywhere in ro:
- reads are free (memory, archive, loops, approvals list).
- ro_message_user writes to YOUR channel only (self-channel under the
  house rules) and lands in the egress ledger.
- anything outward to other people goes through ro_chat -> the supervisor
  -> an approval card on your phone. an mcp client cannot bypass the gate,
  because the gate is below it.
- vault rows never surface here: the server runs in the cloud lane.
"""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

mcp = MCPServer("ro", instructions=(
    "ro is the user's personal agent os. reads are free; ro_message_user "
    "reaches only the user themselves; anything outward to other people "
    "goes through ro_chat and waits at the user's approval gate."
))


@mcp.tool()
async def ro_chat(text: str) -> str:
    """talk to ro's full supervisor: memory, agents, tools. outward writes
    open approval cards for the user; this call cannot bypass the gate."""
    import uuid
    from api.memory.db import db
    from api.observability import budget
    from api.supervisor import run_supervisor

    budget.set_run("mcp-client")
    row = await db.fetchrow(
        """insert into channel_sessions (channel, chat_key) values ('mcp', 'client')
           on conflict (channel, chat_key) do update set chat_key = excluded.chat_key
           returning session_id""",
    )
    result = await run_supervisor(session_id=row["session_id"], user_text=text)
    return (result.get("text") or "").strip() or "(no reply)"


@mcp.tool()
async def ro_memory_search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """hybrid search over ro's memory (profile, conversations, decisions).
    vault rows are never returned."""
    from api.memory.retrieval import retrieve_relevant

    items = await retrieve_relevant(query, limit=min(limit, 20))
    return [
        {"kind": i.get("kind"), "body": (i.get("body") or "")[:500],
         "score": i.get("score")}
        for i in items
    ]


@mcp.tool()
async def ro_archive_search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """search the lifetime message archive (imessage + email history)."""
    from api.memory.backfill import search_archive

    return await search_archive(query, limit=min(limit, 30), vault_visible=False)


@mcp.tool()
async def ro_open_loops() -> list[dict[str, Any]]:
    """open commitments in both directions, with age in days."""
    from api.memory.commitments import open_loops

    return await open_loops()


@mcp.tool()
async def ro_add_loop(direction: str, who: str, what: str, due_hint: str = "") -> str:
    """file a commitment ro should track (direction: mine|theirs)."""
    from api.memory.db import db

    if direction not in ("mine", "theirs"):
        return "direction must be 'mine' or 'theirs'"
    await db.execute(
        """insert into commitments (direction, who, what, due_hint, source)
           values ($1, $2, $3, $4, 'mcp')""",
        direction, who[:200], what[:400], due_hint[:120],
    )
    return f"tracked: [{direction}] {what}"


@mcp.tool()
async def ro_pending_approvals() -> list[dict[str, Any]]:
    """approval cards currently waiting on the user. read-only here:
    deciding stays on the user's own surfaces."""
    from api.supervisor import approval

    rows = await approval.list_pending()
    return [
        {"id": r["id"], "tool": r["tool"], "description": r["description"]}
        for r in rows
    ]


@mcp.tool()
async def ro_message_user(text: str) -> str:
    """send the user a message through their own ro channels (imessage /
    telegram / push). self-channel write: allowed by the house rules,
    recorded in the egress ledger."""
    from api.digest import deliver

    outcomes = await deliver(text[:2000])
    delivered = [k for k, v in outcomes.items() if v]
    return f"delivered via: {', '.join(delivered) or 'no channel configured'}"


@mcp.tool()
async def ro_run_playbook(name: str, shadow: bool = False) -> dict[str, Any]:
    """run a saved playbook. shadow=true dry-runs with zero egress."""
    from api.playbooks import run_playbook

    return await run_playbook(name, shadow=shadow)


if __name__ == "__main__":
    mcp.run()
