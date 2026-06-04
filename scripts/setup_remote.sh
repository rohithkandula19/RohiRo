#!/usr/bin/env bash
# setup remote access to ro for the iOS shortcut.
# generates a bearer token, stores it in keychain, prints the URL to use.
set -euo pipefail

# 1. generate a random secret
SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
keyring set ro remote_secret <<< "$SECRET"
echo "saved remote_secret to ro keychain"
echo

# 2. figure out reachable hostnames
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "")
TS_IP=$(/Applications/Tailscale.app/Contents/MacOS/Tailscale ip --4 2>/dev/null || command tailscale ip --4 2>/dev/null | head -1 || echo "")

echo "── reachable endpoints ──"
[ -n "$LAN_IP" ] && echo "  LAN       : http://$LAN_IP:8000"
[ -n "$TS_IP" ]  && echo "  Tailscale : http://$TS_IP:8000   (works anywhere)"
echo
echo "── bearer token (paste into iOS Shortcut) ──"
echo "  $SECRET"
echo
echo "── one-page iOS install wizard. open on your iPhone: ──"
ENC=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$SECRET")
[ -n "$LAN_IP" ] && echo "  LAN       : http://$LAN_IP:8000/install/ios.html?token=$ENC"
[ -n "$TS_IP" ]  && echo "  Tailscale : http://$TS_IP:8000/install/ios.html?token=$ENC"
echo
echo "── api must bind 0.0.0.0 to be reachable. one-shot:"
echo "    RO_API_HOST=0.0.0.0 RO_REMOTE_SECRET_OK=1 uv run uvicorn api.main:app --host 0.0.0.0 --port 8000"
echo "  or set RO_API_HOST=0.0.0.0 in your launchd plist (infra/launchd/ro.api.plist)."
