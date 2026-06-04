# Talk to ro from your iPhone

A 12-step iOS Shortcut that records you talking, sends it to ro on your mac, plays the reply.

Works on iOS Shortcuts, Apple Watch, Hey Siri, and Home Screen tap.

---

## 1. one-time setup on your mac

```bash
# 1. generate a bearer token and print your reachable URLs:
./scripts/setup_remote.sh

# 2. bind the api to 0.0.0.0 so the phone can reach it:
#    edit infra/launchd/ro.api.plist — change --host 127.0.0.1 to --host 0.0.0.0
#    then:
launchctl unload ~/Library/LaunchAgents/ro.api.plist
launchctl load -w ~/Library/LaunchAgents/ro.api.plist
```

You'll need a stable address the phone can hit:

- **same wifi** — your mac's LAN IP (printed by setup_remote.sh). cheap but breaks the moment you leave the house.
- **anywhere** — install [Tailscale](https://tailscale.com) on the mac and the phone (free for personal use). The mac's `tailscale ip --4` is your endpoint. ro is reachable from your couch, an Uber, an airport, anywhere.

---

## 2. build the Shortcut (one-time, 5 min)

Open **Shortcuts** on your iPhone → tap the **+** in the top right.

Name it: **Talk to ro**.

Add these actions, in order:

```
1.  Record Audio
       • Audio Quality: Normal
       • Start Recording: On Tap
       • Stop Recording: On Tap

2.  Get Contents of URL                ← the meat of the shortcut
       URL:    http://<your-mac-ip>:8000/api/voice/talk
       Method: POST
       Request Body: Form
         File: Recorded Audio          (the variable from step 1)
       Headers:
         Authorization: Bearer <your-token-from-setup_remote.sh>

3.  Play Sound
       Sound: Contents of URL          (the audio mp3 ro sent back)
```

Tap **Done**.

### add Hey Siri (optional)

Tap the Shortcut → ⓘ → "Add to Siri" → say "Hey Siri, talk to ro" — done.

### add to Home Screen (optional)

Same ⓘ panel → "Add to Home Screen" → choose icon. One-tap mic from your lock screen.

---

## 3. text-based alternative

If you want "Hey Siri, ask ro what's on my calendar today" without recording audio:

```
1.  Ask for Input                       ← lets Siri dictate the text
       Prompt: "ask ro"
       Default Answer: (blank)
       Input Type: Text

2.  Get Contents of URL
       URL:    http://<mac-ip>:8000/api/voice/ask
       Method: POST
       Request Body: JSON
         text: Provided Input           (the dictated text)
       Headers:
         Authorization: Bearer <token>

3.  Play Sound: Contents of URL
```

This is faster because there's no audio upload — Siri does the dictation locally.

---

## 4. what the endpoints do

| | endpoint | takes | returns |
|---|---|---|---|
| audio in, audio out | `POST /api/voice/talk` | audio file (m4a / webm / wav) | mp3 + `X-Ro-Transcript` / `X-Ro-Reply` headers |
| text in, audio out  | `POST /api/voice/ask`  | json: `{ "text": "..." }`     | mp3 + `X-Ro-Reply` header |

Both require `Authorization: Bearer <remote_secret>` if you set one.

---

## 5. troubleshooting

- **Shortcut hangs.** Check `RO_API_HOST=0.0.0.0` — by default the api is 127.0.0.1 only. Your phone can't see localhost.
- **401 Unauthorized.** Bearer token in the Shortcut header doesn't match `keyring get ro remote_secret` on the mac.
- **Plays silence.** Open the chat at `localhost:3000` and check if the same question works there. If not, it's an api/model issue, not the Shortcut.
- **"no speech detected".** Whisper didn't pick up audio. Hold the phone closer to your mouth; try Hey Siri version instead.
- **Slow.** First request after a cold start takes ~3-5s (whisper warmup + claude latency). Subsequent calls under 2s.
