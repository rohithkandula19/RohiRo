"""ro cli. talks to the same supervisor the web ui talks to."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown

app = typer.Typer(no_args_is_help=True, add_completion=False, help="ro cli")
console = Console()

ROOT = Path(__file__).resolve().parent.parent


@app.command()
def chat(text: str | None = typer.Argument(None)) -> None:
    """one-shot chat. with no args, opens an interactive prompt."""

    from api.supervisor import run_supervisor

    async def once(q: str) -> None:
        result = await run_supervisor(session_id=uuid.uuid4(), user_text=q)
        console.print(Markdown(result.get("text", "") or "(empty)"))

    if text:
        asyncio.run(once(text))
        return

    console.print("[dim]type a message. ctrl-d to quit.[/dim]")
    try:
        while True:
            q = input("you: ").strip()
            if not q:
                continue
            asyncio.run(once(q))
    except (EOFError, KeyboardInterrupt):
        console.print()


@app.command()
def status() -> None:
    """run the local healthcheck."""

    subprocess.run([str(ROOT / "scripts" / "healthcheck.sh")], check=False)


@app.command(name="up")
@app.command()
def start() -> None:
    """install + start the launchd services (api hosts the listeners in-process)."""

    plist_dir = ROOT / "infra" / "launchd"
    target = Path.home() / "Library" / "LaunchAgents"
    target.mkdir(parents=True, exist_ok=True)
    for plist in plist_dir.glob("*.plist"):
        dst = target / plist.name
        dst.write_text(plist.read_text())
        subprocess.run(["launchctl", "unload", str(dst)], check=False)
        subprocess.run(["launchctl", "load", str(dst)], check=False)
        console.print(f"[green]loaded[/green] {plist.name}")


@app.command(name="down")
@app.command()
def stop() -> None:
    """stop the launchd services."""

    target = Path.home() / "Library" / "LaunchAgents"
    for plist in target.glob("ro.*.plist"):
        subprocess.run(["launchctl", "unload", str(plist)], check=False)
        console.print(f"[yellow]unloaded[/yellow] {plist.name}")


@app.command()
def export() -> None:
    """export your whole agent (db dump + playbooks) to ~/ro-exports."""

    from api.export import main as export_main
    asyncio.run(export_main())


@app.command()
def skills(query: str | None = typer.Argument(None)) -> None:
    """browse the agent-skills catalog ro can run (anthropic SKILL.md format)."""

    from api.skills_bridge import catalog

    async def _list() -> None:
        found = await catalog(query=query, limit=30)
        if not found:
            console.print("[dim]no skills found. drop SKILL.md folders in ~/.claude/skills or ./skills[/dim]")
            return
        for s in found:
            console.print(f"[bold]{s['name']}[/bold]  [dim]{s['description'][:70]}[/dim]")

    asyncio.run(_list())


@app.command()
def doctor() -> None:
    """diagnose everything: keys, permissions, services, models. the
    go-live dry run — every red line comes with its fix."""

    import shutil as _shutil

    def check(label: str, ok: bool, fix: str = "") -> None:
        mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
        line = f"{mark} {label}"
        if not ok and fix:
            line += f"  [dim]→ {fix}[/dim]"
        console.print(line)

    async def run_checks() -> None:
        from api.config import secrets

        console.print("[bold]ro doctor[/bold]\n")

        # keys
        for key, why in [
            ("anthropic_api_key", "the brain. console.anthropic.com/settings/keys (or set openrouter_api_key)"),
            ("openrouter_api_key", "alt brain via openrouter.ai/keys — text paths only"),
            ("imessage_channel", "your own number. keyring set ro imessage_channel"),
            ("user_email", "keyring set ro user_email"),
            ("telegram_bot_token", "optional. @BotFather"),
            ("openai_api_key", "optional: embeddings + voice fallback"),
            ("vapid_private_key", "uv run python -m api.integrations.webpush --generate"),
        ]:
            check(f"keychain: {key}", bool(secrets.get(key)), why)

        # database
        pg_ok = False
        try:
            from api.memory.db import db
            await asyncio.wait_for(db.pg(), timeout=3)
            await db.fetchrow("select 1 from action_log limit 1")
            pg_ok = True
        except Exception:
            pass
        check("postgres reachable + schema applied", pg_ok,
              "brew services start postgresql@17 (port 5435) or docker compose up -d, then scripts/bootstrap.sh")

        # api
        api_ok = False
        try:
            import httpx as _httpx
            api_ok = _httpx.get("http://127.0.0.1:8000/health", timeout=3).status_code == 200
        except Exception:
            pass
        check("api answering on :8000", api_ok, "uv run ro up")

        # mac permissions
        from api.integrations import imessage as imsg
        check("chat.db readable (full disk access)", imsg.configured(),
              "System Settings → Privacy & Security → Full Disk Access → your terminal")

        # local tier
        check("ffmpeg (local whisper)", _shutil.which("ffmpeg") is not None, "brew install ffmpeg")
        ollama_ok = False
        try:
            import httpx as _httpx
            ollama_ok = _httpx.get("http://127.0.0.1:11434/api/tags", timeout=2).status_code == 200
        except Exception:
            pass
        check("ollama (local model tier)", ollama_ok, "optional: brew install ollama && ollama pull llama3.2:3b")

        console.print("\n[dim]red lines block the matching feature only. ./scripts/go_live.sh fixes the required ones interactively.[/dim]")

    asyncio.run(run_checks())


@app.command()
def playbooks() -> None:
    """list saved playbooks."""

    import httpx as _httpx
    try:
        r = _httpx.get("http://127.0.0.1:8000/api/playbooks", timeout=5)
        for p in r.json():
            console.print(f"[bold]{p['name']}[/bold]  {p['title']}  ({p['steps']} steps)")
        if not r.json():
            console.print("[dim]no playbooks yet. see playbooks/README.md[/dim]")
    except Exception:
        console.print("[red]api not reachable — is `ro up` running?[/red]")


def main() -> None:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("PYTHONPATH", str(ROOT))
    app()


if __name__ == "__main__":
    main()
