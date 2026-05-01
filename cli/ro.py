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


@app.command()
def start() -> None:
    """install + start the launchd services (imessage, telegram, voice, jobs)."""

    plist_dir = ROOT / "infra" / "launchd"
    target = Path.home() / "Library" / "LaunchAgents"
    target.mkdir(parents=True, exist_ok=True)
    for plist in plist_dir.glob("*.plist"):
        dst = target / plist.name
        dst.write_text(plist.read_text())
        subprocess.run(["launchctl", "unload", str(dst)], check=False)
        subprocess.run(["launchctl", "load", str(dst)], check=False)
        console.print(f"[green]loaded[/green] {plist.name}")


@app.command()
def stop() -> None:
    """stop the launchd services."""

    target = Path.home() / "Library" / "LaunchAgents"
    for plist in target.glob("ro.*.plist"):
        subprocess.run(["launchctl", "unload", str(plist)], check=False)
        console.print(f"[yellow]unloaded[/yellow] {plist.name}")


def main() -> None:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("PYTHONPATH", str(ROOT))
    app()


if __name__ == "__main__":
    main()
