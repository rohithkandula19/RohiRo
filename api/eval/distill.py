"""distill-down data prep. export edit pairs for a local fine-tune.

every time you edit a draft, two places remember it: voice_signals
(decision='edited', original vs edited) and action_log (edit_note, with
the original body in the payload). this module turns those into chat
format training pairs and writes them as jsonl, ready for lora tuning.

downstream recipe, once you have a file:

  1. tune a small local model with mlx-lm on apple silicon:

       uv run mlx_lm.lora \\
         --model mlx-community/Llama-3.2-3B-Instruct-4bit \\
         --train --data ~/ro-exports \\
         --iters 300 --batch-size 2 --learning-rate 1e-5

     (mlx expects train.jsonl in the data dir; symlink or copy
     distill-pairs.jsonl there. qwen works too, e.g.
     mlx-community/Qwen2.5-3B-Instruct-4bit.)

  2. promotion gate: before pointing the ollama_model preference at the
     tuned model, run the repo evals (api/eval/harness.py) against it.
     no eval pass, no promotion.

  3. honest caveat: at low data volumes (tens of pairs) a lora mostly
     memorizes. few-shot prompting with the learned-style rules from
     voice_learner often beats it. distill when the export count is in
     the hundreds; until then this file is a progress meter.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from api.memory.db import db
from api.observability.logging import log

SYSTEM_PROMPT = "you draft messages in the user's voice."

DEFAULT_OUT = "~/ro-exports/distill-pairs.jsonl"


# ----- pure helpers -----


def build_pair(channel: str, original: str, edited: str) -> dict[str, Any]:
    """one chat-format training pair. the channel rides along as context."""
    user = f"channel: {channel}\ndraft:\n{original}"
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
            {"role": "assistant", "content": edited},
        ]
    }


def dedupe_pairs(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """drop identical pairs, first occurrence wins. order preserved."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for p in pairs:
        key = json.dumps(p, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def refuse_below_min(n_pairs: int, min_pairs: int) -> Optional[dict[str, Any]]:
    """a fine-tune on 5 examples is noise. return the refusal, or none."""
    if n_pairs < min_pairs:
        return {
            "exported": 0,
            "reason": f"only {n_pairs} pairs, need {min_pairs}. keep editing drafts.",
        }
    return None


def _channel_for(tool: str) -> str:
    if tool.startswith("gmail."):
        return "gmail"
    if tool.startswith("slack."):
        return "slack"
    if tool.startswith("imessage."):
        return "imessage"
    if tool.startswith("calendar."):
        return "calendar"
    return "other"


# ----- export -----


async def _signal_pairs() -> list[dict[str, Any]]:
    rows = await db.fetch(
        """select channel, original, edited from voice_signals
           where decision = 'edited' and original <> '' and edited <> ''
           order by created_at asc"""
    )
    return [build_pair(r["channel"], r["original"], r["edited"]) for r in rows]


async def _action_pairs() -> list[dict[str, Any]]:
    rows = await db.fetch(
        """select tool, payload, edit_note from action_log
           where edit_note is not null and edit_note <> ''
           order by created_at asc"""
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        payload = r["payload"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                continue
        if not isinstance(payload, dict):
            continue
        original = str(payload.get("body") or payload.get("content") or "")
        if not original.strip():
            continue
        out.append(build_pair(_channel_for(r["tool"]), original, r["edit_note"]))
    return out


async def export_pairs(out_path: str | None = None, min_pairs: int = 20) -> dict[str, Any]:
    """pull edit pairs from voice_signals + action_log, write jsonl."""
    pairs = dedupe_pairs(await _signal_pairs() + await _action_pairs())

    refusal = refuse_below_min(len(pairs), min_pairs)
    if refusal:
        return refusal

    path = os.path.expanduser(out_path or DEFAULT_OUT)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    log.info("distill pairs exported", n=len(pairs), path=path)
    return {"exported": len(pairs), "path": path}
