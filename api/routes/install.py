"""install routes — a one-page wizard the user opens on their phone.

served at GET /install/ios.html?token=<bearer>&base=<api-url>

shows:
  • a copy-to-clipboard URL pointing at /api/voice/talk
  • a copy-to-clipboard bearer token
  • the 4 actions to add in Shortcuts.app (record → http → play → done)
  • a deep link that opens Shortcuts.app at "new shortcut"

no auth required (the page itself reveals nothing about the system; the
token in the query param is only useful if the api is exposed publicly,
which is the user's choice via setup_remote.sh).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <title>install · ro</title>
  <style>
    :root {{
      --bg: #FAFAFA; --surface: #FFFFFF; --ink: #1F2023; --ink-muted: #62656D;
      --ink-subtle: #8E919A; --accent: #5E6AD2; --accent-soft: #EEF0FB;
      --line: rgba(0,0,0,0.08); --line-strong: rgba(0,0,0,0.12);
      --warning: #F2994A; --success: #4CB782;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{ --bg: #18181a; --surface: #1f2024; --ink: #f3f3f5; --ink-muted: #b5b8c0;
              --ink-subtle: #8a8d97; --line: rgba(255,255,255,0.10); --line-strong: rgba(255,255,255,0.16);
              --accent: #8a96f3; --accent-soft: rgba(138,150,243,0.18); }}
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ background: var(--bg); color: var(--ink); margin: 0;
      font: 15px/1.55 -apple-system, system-ui, sans-serif;
      padding-bottom: env(safe-area-inset-bottom);
    }}
    .wrap {{ max-width: 560px; margin: 0 auto; padding: 24px 18px 80px; }}
    .logo {{ display:inline-flex; align-items:center; gap:10px; }}
    .logo .badge {{ width: 36px; height: 36px; border-radius: 9px; background: var(--accent);
      color: white; display:flex; align-items:center; justify-content:center; font-weight:600; font-size:18px; }}
    h1 {{ font-size: 24px; font-weight: 600; letter-spacing: -0.02em; margin: 18px 0 4px; }}
    .lead {{ color: var(--ink-muted); margin: 0 0 24px; font-size: 14px; }}
    .card {{ background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
      padding: 14px 16px; margin: 12px 0; }}
    .label {{ color: var(--ink-subtle); font-size: 11px; text-transform: uppercase;
      letter-spacing: 0.05em; font-weight: 600; margin-bottom: 6px; }}
    .copy {{ display:flex; align-items:center; gap:10px; }}
    .copy code {{ flex: 1; font: 12.5px/1.4 ui-monospace, monospace; color: var(--ink);
      background: var(--accent-soft); padding: 9px 11px; border-radius: 7px;
      word-break: break-all; user-select: all; }}
    button {{ font: 13px -apple-system, system-ui, sans-serif; font-weight: 500;
      background: var(--accent); color: white; border: 0; border-radius: 7px;
      padding: 9px 14px; cursor: pointer; -webkit-tap-highlight-color: transparent; }}
    button.copied {{ background: var(--success); }}
    button.ghost {{ background: transparent; color: var(--ink); border: 1px solid var(--line); }}
    .step {{ display:flex; gap: 12px; margin: 8px 0; }}
    .step .num {{ flex:0 0 26px; width: 26px; height: 26px; border-radius: 50%;
      background: var(--accent-soft); color: var(--accent);
      display:flex; align-items:center; justify-content:center; font-weight:600; font-size:12.5px; }}
    .step .body {{ font-size: 14px; }}
    .step .body code {{ font: 12.5px ui-monospace, monospace; color: var(--ink); background: var(--accent-soft); padding: 1px 5px; border-radius: 4px; }}
    .open {{ display:block; margin: 18px 0; text-align: center; padding: 13px;
      background: var(--accent); color: white !important; text-decoration: none;
      border-radius: 10px; font-weight: 600; font-size: 15px; }}
    .footer {{ margin-top: 28px; color: var(--ink-subtle); font-size: 12px; text-align: center; }}
    .warn {{ background: rgba(242, 153, 74, 0.08); border-color: rgba(242, 153, 74, 0.25); }}
    .warn .label {{ color: var(--warning); }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="logo">
      <div class="badge">r</div>
      <strong>ro · iOS install</strong>
    </div>

    <h1>Talk to ro from your iPhone.</h1>
    <p class="lead">One Shortcut. 4 actions. Hold the button → talk → ro replies.</p>

    <div class="card">
      <div class="label">1. URL</div>
      <div class="copy">
        <code id="url">{url}</code>
        <button onclick="copy('url', this)">Copy</button>
      </div>
    </div>

    <div class="card">
      <div class="label">2. Bearer token</div>
      <div class="copy">
        <code id="tok">{token}</code>
        <button onclick="copy('tok', this)">Copy</button>
      </div>
      {token_note}
    </div>

    <a class="open" href="shortcuts://create-shortcut">Open Shortcuts.app</a>

    <div class="card">
      <div class="label">3. Build the shortcut</div>
      <div class="step"><div class="num">1</div><div class="body">Name it <code>Talk to ro</code>.</div></div>
      <div class="step"><div class="num">2</div><div class="body">Add <strong>Record Audio</strong>. Set <em>Stop Recording</em> to <code>On Tap</code>.</div></div>
      <div class="step"><div class="num">3</div><div class="body">Add <strong>Get Contents of URL</strong>:<br>
        • Tap the URL → paste the copied URL.<br>
        • Method: <code>POST</code>. Request Body: <code>Form</code>. Field <code>audio</code> → <em>Recorded Audio</em>.<br>
        • Headers: <code>Authorization</code> = <code>Bearer &lt;paste token&gt;</code>.</div></div>
      <div class="step"><div class="num">4</div><div class="body">Add <strong>Play Sound</strong> → use <em>Contents of URL</em>.</div></div>
      <div class="step"><div class="num">5</div><div class="body">Done. Tap the shortcut → talk → ro answers out loud.</div></div>
    </div>

    <div class="card">
      <div class="label">Make it instant</div>
      <div class="step"><div class="num">A</div><div class="body">Tap <strong>Add to Home Screen</strong> for a one-tap mic button anywhere.</div></div>
      <div class="step"><div class="num">B</div><div class="body">Tap <strong>Add to Siri</strong> → say "Hey Siri, talk to ro" for hands-free.</div></div>
    </div>

    {warn_card}

    <p class="footer">ro — your agent.</p>
  </div>

  <script>
    function copy(id, btn) {{
      const el = document.getElementById(id);
      const text = el.textContent;
      const done = () => {{ btn.classList.add('copied'); btn.textContent = 'Copied'; setTimeout(()=>{{btn.classList.remove('copied');btn.textContent='Copy';}}, 1400); }};
      if (navigator.clipboard) {{ navigator.clipboard.writeText(text).then(done, ()=>{{document.execCommand('copy');done();}}); return; }}
      const range = document.createRange(); range.selectNode(el); window.getSelection().removeAllRanges(); window.getSelection().addRange(range);
      document.execCommand('copy'); done();
    }}
  </script>
</body>
</html>"""


@router.get("/install/ios.html", response_class=HTMLResponse)
async def ios_install(request: Request, token: str = "", base: str = "") -> HTMLResponse:
    # default base to the host the request came in on
    if not base:
        # request.url is the full incoming URL; build api base from it
        scheme = request.url.scheme
        host = request.headers.get("host") or request.url.netloc
        base = f"{scheme}://{host}"
    url = f"{base.rstrip('/')}/api/voice/talk"

    token_display = token or "<paste your bearer token here>"
    token_note = (
        "" if token else
        '<p class="lead" style="margin: 8px 0 0; font-size: 12.5px;">'
        'Run <code>./scripts/setup_remote.sh</code> on your mac and paste the token it prints '
        'into the Shortcut\'s Authorization header. Keep tokens out of URLs.</p>'
    )

    warn_card = ""
    if base.startswith("http://") and not base.startswith("http://localhost") and not base.startswith("http://127."):
        warn_card = (
            '<div class="card warn">'
            '<div class="label">heads up</div>'
            '<div style="font-size: 13.5px; line-height: 1.55;">'
            'This URL is <strong>http</strong>, not https. The bearer token will travel in clear text. '
            'Use Tailscale or a TLS reverse proxy before exposing ro outside your LAN.'
            '</div></div>'
        )

    html = _PAGE.format(
        url=url, token=token_display, token_note=token_note, warn_card=warn_card
    )
    return HTMLResponse(html)
