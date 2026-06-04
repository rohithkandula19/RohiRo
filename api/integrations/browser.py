"""playwright browser.

three modes:

  one-shot (`render(url)`):  fresh context. returns text+screenshot.
  ephemeral session:          persistent across steps in one task; no cookies
                              outlive the session.
  trusted-host session:       reuses ~/ro/browser-profiles/<host>/ as a
                              persistent chromium user-data-dir. cookies +
                              localStorage + indexeddb persist across sessions
                              so ro can act on logged-in sites.

profile trust is opt-in: a profile dir must exist for a host before the
session uses it. one-time login per host is done via
`uv run python -m api.integrations.browser login <host>`.

safety rails for the session paths:
  - per-step approval (integration never runs without `execute()`)
  - hard-deny click text and URLs matching purchase/transfer/submit patterns
  - max 25 actions per session; after that the user has to restart
  - 5-minute idle timeout
  - profiles are scoped to a single host (no cookie bleed across hosts)
"""

from __future__ import annotations

import asyncio
import base64
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from api.observability.logging import log

PROFILE_ROOT = Path.home() / "ro" / "browser-profiles"

DEFAULT_TIMEOUT_MS = 25_000
DEFAULT_VIEWPORT = (1280, 800)

# urls and click-text we refuse to act on. read-only browsing is fine; the rail
# kicks in only when ro is asked to *do* something (click/fill/submit).
CLICK_DENY_PATTERNS = [
    r"\b(pay|buy|purchase|checkout|order now|place order|confirm( order)?|complete (purchase|order))\b",
    r"\bsubmit (payment|order|application|cv|resume|return)\b",
    r"\btransfer\b.*\b(funds|money)\b",
    r"\bdelete (account|everything|all)\b",
]
URL_DENY_PATTERNS = [
    r"checkout", r"/cart", r"/pay", r"/payment", r"/billing", r"/transfer",
    r"banking", r"/transactions", r"wire-?transfer", r"venmo\.com/checkout",
]
MAX_ACTIONS_PER_SESSION = 25
SESSION_IDLE_TIMEOUT_S = 5 * 60


@dataclass
class RenderResult:
    url: str
    final_url: str
    title: str
    text: str
    screenshot_b64: str
    status: int = 0
    truncated: bool = False


@dataclass
class StepResult:
    action: str            # goto | click | fill | scroll | close
    final_url: str
    title: str
    text: str              # rendered text snippet (post-action)
    screenshot_b64: str
    elements: list[dict]   # what's clickable/fillable, for the next step
    truncated: bool = False
    note: str = ""


def configured() -> bool:
    return True


# ----- v1: one-shot render -----


async def render(
    url: str,
    *,
    wait_until: str = "networkidle",
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    text_cap: int = 16000,
    take_screenshot: bool = True,
) -> RenderResult:
    if not url.startswith(("http://", "https://")):
        raise RuntimeError("browser.render needs an http(s) url")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(
                viewport={"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]},
                user_agent=_ua(),
            )
            page = await ctx.new_page()
            try:
                resp = await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            except Exception as e:
                log.warning("browser goto failed", url=url, error=str(e))
                resp = None
            status = resp.status if resp else 0
            final_url = page.url
            title = await page.title()
            try:
                text = await page.evaluate("document.body && document.body.innerText || ''")
            except Exception:
                text = ""
            truncated = False
            if text and len(text) > text_cap:
                text = text[:text_cap] + f"\n\n…[truncated at {text_cap} chars]"
                truncated = True
            shot = ""
            if take_screenshot:
                try:
                    png = await page.screenshot(full_page=False, type="png")
                    shot = base64.b64encode(png).decode("ascii")
                except Exception:
                    pass
            return RenderResult(
                url=url, final_url=final_url, title=title or "",
                text=text or "", screenshot_b64=shot,
                status=status, truncated=truncated,
            )
        finally:
            await browser.close()


# ----- v2: persistent sessions -----


def _host_of(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _profile_dir_for(host: Optional[str]) -> Optional[Path]:
    """return the path to a host's persistent profile if it exists, else None."""
    if not host:
        return None
    p = PROFILE_ROOT / host
    return p if p.exists() else None


def list_profiles() -> list[str]:
    """all hosts that have an existing profile directory."""
    if not PROFILE_ROOT.exists():
        return []
    return sorted(d.name for d in PROFILE_ROOT.iterdir() if d.is_dir())


def ensure_profile_root() -> None:
    PROFILE_ROOT.mkdir(parents=True, exist_ok=True)


class Session:
    """one persistent chromium tab. agents call verbs; each verb is approved separately."""

    def __init__(self, key: str):
        self.key = key
        self._pw = None
        self._browser: Optional[Browser] = None
        self._ctx: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._action_count = 0
        self._last_used = time.time()
        self._profile_host: Optional[str] = None   # which host's profile we're locked to (if any)

    async def _ensure(self, *, url: Optional[str] = None) -> Page:
        if self._page is not None:
            self._last_used = time.time()
            return self._page

        self._pw = await async_playwright().start()
        host = _host_of(url)
        profile_dir = _profile_dir_for(host)

        if profile_dir is not None:
            # persistent context: cookies+storage persist across sessions
            log.info("browser session using persistent profile", host=host, dir=str(profile_dir))
            self._ctx = await self._pw.chromium.launch_persistent_context(
                str(profile_dir),
                headless=True,
                viewport={"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]},
                user_agent=_ua(),
            )
            self._browser = None
            self._page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()
            self._profile_host = host
        else:
            # ephemeral
            self._browser = await self._pw.chromium.launch(headless=True)
            self._ctx = await self._browser.new_context(
                viewport={"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]},
                user_agent=_ua(),
            )
            self._page = await self._ctx.new_page()

        self._last_used = time.time()
        return self._page

    async def goto(self, url: str) -> StepResult:
        _assert_url_ok(url)
        # warn if a session locked to one profile is being navigated to a different host
        if self._page is not None and self._profile_host:
            target_host = _host_of(url)
            if target_host and target_host != self._profile_host:
                log.warning(
                    "browser session locked to a profile; navigating off-host",
                    locked_to=self._profile_host, target=target_host,
                )
        page = await self._ensure(url=url)
        self._bump()
        try:
            await page.goto(url, wait_until="networkidle", timeout=DEFAULT_TIMEOUT_MS)
        except Exception as e:
            log.warning("session goto failed", url=url, error=str(e))
        return await self._snapshot("goto")

    async def click(self, text: str) -> StepResult:
        page = await self._ensure()
        _assert_click_text_ok(text)
        self._bump()
        loc = page.get_by_role("button", name=text)
        try:
            if await loc.count() == 0:
                loc = page.get_by_role("link", name=text)
            if await loc.count() == 0:
                loc = page.get_by_text(text, exact=False).first
            await loc.click(timeout=DEFAULT_TIMEOUT_MS)
        except Exception as e:
            return await self._snapshot("click", note=f"click failed: {e}")
        try:
            await page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT_MS)
        except Exception:
            pass
        return await self._snapshot("click")

    async def fill(self, label: str, value: str) -> StepResult:
        page = await self._ensure()
        _assert_click_text_ok(label)  # same guardrails for input labels
        self._bump()
        # try several strategies to find a labeled input
        loc = page.get_by_label(label, exact=False)
        try:
            if await loc.count() == 0:
                loc = page.get_by_placeholder(label)
            if await loc.count() == 0:
                loc = page.get_by_role("textbox", name=label)
            await loc.fill(value, timeout=DEFAULT_TIMEOUT_MS)
        except Exception as e:
            return await self._snapshot("fill", note=f"fill failed: {e}")
        return await self._snapshot("fill")

    async def scroll(self, pixels: int = 600) -> StepResult:
        page = await self._ensure()
        self._bump()
        try:
            await page.evaluate(f"window.scrollBy(0, {int(pixels)})")
            await asyncio.sleep(0.4)
        except Exception:
            pass
        return await self._snapshot("scroll")

    async def close(self) -> StepResult:
        # snapshot one final state for the log, then tear down
        try:
            snap = await self._snapshot("close")
        except Exception:
            snap = StepResult(action="close", final_url="", title="", text="",
                              screenshot_b64="", elements=[])
        await self._teardown()
        return snap

    # ----- internals -----

    def _bump(self) -> None:
        self._action_count += 1
        if self._action_count > MAX_ACTIONS_PER_SESSION:
            raise RuntimeError(f"session hit the {MAX_ACTIONS_PER_SESSION}-action cap. close and start a new task.")

    async def _snapshot(self, action: str, *, note: str = "") -> StepResult:
        page = self._page
        if page is None:
            return StepResult(action=action, final_url="", title="", text="",
                              screenshot_b64="", elements=[], note=note)
        try:
            title = await page.title()
            text = await page.evaluate("document.body && document.body.innerText || ''")
            png = await page.screenshot(full_page=False, type="png")
            shot = base64.b64encode(png).decode("ascii")
            elements = await self._extract_elements()
        except Exception as e:
            log.warning("snapshot failed", error=str(e))
            return StepResult(action=action, final_url=page.url, title="", text="",
                              screenshot_b64="", elements=[], note=note or str(e))
        truncated = False
        if text and len(text) > 6000:
            text = text[:6000] + "…[truncated]"
            truncated = True
        return StepResult(
            action=action, final_url=page.url, title=title or "",
            text=text or "", screenshot_b64=shot, elements=elements,
            truncated=truncated, note=note,
        )

    async def _extract_elements(self) -> list[dict]:
        """list the page's clickable/fillable elements, with stable labels."""
        page = self._page
        if not page:
            return []
        # tight subset: focus on a useful nav surface for the next step
        try:
            data = await page.evaluate(
                """() => {
                  const out = [];
                  const seen = new Set();
                  function add(kind, label, extra) {
                    label = (label || "").trim().slice(0, 80);
                    if (!label) return;
                    const key = kind + "::" + label;
                    if (seen.has(key)) return;
                    seen.add(key);
                    out.push({kind, label, ...(extra || {})});
                  }
                  document.querySelectorAll('a[href]').forEach(a => add('link', a.innerText));
                  document.querySelectorAll('button').forEach(b => add('button', b.innerText));
                  document.querySelectorAll('input,textarea,select').forEach(i => {
                    const name = i.getAttribute('aria-label') || i.getAttribute('placeholder') || i.name || '';
                    add('input', name, {type: i.type || i.tagName.toLowerCase()});
                  });
                  return out.slice(0, 40);
                }"""
            )
            return list(data or [])
        except Exception:
            return []

    async def _teardown(self) -> None:
        try:
            if self._ctx:
                await self._ctx.close()
        except Exception:
            pass
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self._page = self._ctx = self._browser = self._pw = None


_SESSIONS: dict[str, Session] = {}
_GC_LOCK = asyncio.Lock()


async def get_session(key: str) -> Session:
    """get-or-create a session for this task. lazily GCs idle ones."""
    async with _GC_LOCK:
        # GC: drop idle sessions before handing one out
        stale = [k for k, s in _SESSIONS.items() if time.time() - s._last_used > SESSION_IDLE_TIMEOUT_S]
        for k in stale:
            try:
                await _SESSIONS[k]._teardown()
            except Exception:
                pass
            _SESSIONS.pop(k, None)
        if key not in _SESSIONS:
            _SESSIONS[key] = Session(key=key)
        return _SESSIONS[key]


async def close_session(key: str) -> bool:
    s = _SESSIONS.pop(key, None)
    if s is None:
        return False
    await s._teardown()
    return True


# ----- safety -----


def _assert_url_ok(url: str) -> None:
    if not url.startswith(("http://", "https://")):
        raise RuntimeError("browser session url must be http(s)")
    lower = url.lower()
    for pat in URL_DENY_PATTERNS:
        if re.search(pat, lower):
            raise RuntimeError(f"refusing browser navigation: url matches deny pattern `{pat}`")


def _assert_click_text_ok(text: str) -> None:
    s = (text or "").lower()
    for pat in CLICK_DENY_PATTERNS:
        if re.search(pat, s):
            raise RuntimeError(f"refusing: target text matches deny pattern `{pat}` (irreversible action class)")


def _ua() -> str:
    return ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 "
            "(KHTML, like Gecko) ro-agent/1.0 Chrome/138 Safari/537.36")


# ----- one-time interactive login (CLI) -----


async def _interactive_login(host: str, start_url: Optional[str] = None) -> None:
    """open a headed chromium with the host's persistent profile.

    the user logs in normally, then closes the window. cookies persist under
    ~/ro/browser-profiles/<host>/ and subsequent ro sessions pick them up.
    """
    ensure_profile_root()
    profile_dir = PROFILE_ROOT / host
    profile_dir.mkdir(parents=True, exist_ok=True)
    url = start_url or f"https://{host}"

    print(f"opening chromium for {host}")
    print(f"  profile dir: {profile_dir}")
    print(f"  starting at: {url}")
    print()
    print("log in, then close the browser window. ro will reuse the cookies.")

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(profile_dir),
            headless=False,
            viewport={"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]},
            user_agent=_ua(),
        )
        try:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
            except Exception:
                pass
            # wait until the user closes every page in the context
            done = asyncio.Event()

            def _on_close(_):
                if not ctx.pages:
                    done.set()

            for pg in ctx.pages:
                pg.on("close", _on_close)
            ctx.on("page", lambda pg: pg.on("close", _on_close))
            try:
                await done.wait()
            except KeyboardInterrupt:
                pass
        finally:
            try:
                await ctx.close()
            except Exception:
                pass
    print(f"profile saved at {profile_dir}")


def _cli() -> int:
    """python -m api.integrations.browser login github.com  [optional-start-url]
    python -m api.integrations.browser list
    """
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__ or "")
        print("usage:")
        print("  python -m api.integrations.browser list")
        print("  python -m api.integrations.browser login <host> [start_url]")
        return 0
    cmd = argv[0]
    if cmd == "list":
        items = list_profiles()
        if not items:
            print("(no profiles yet — run `login <host>` to create one)")
        for h in items:
            print(f"  {h}")
        return 0
    if cmd == "login":
        if len(argv) < 2:
            print("which host? e.g. `login github.com`", file=sys.stderr)
            return 2
        host = argv[1].lower().lstrip("www.")
        start = argv[2] if len(argv) > 2 else None
        asyncio.run(_interactive_login(host, start))
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
