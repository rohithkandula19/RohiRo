# always-on substrate

the laptop sleeps. a small always-on host makes ro truly 24/7: digests at
7am every day, triggers firing while the lid is closed. two good shapes.

## option a: mac mini on your tailnet (best fit)

everything works exactly as on the laptop, imessage included (sign into
messages with your apple id).

1. install: homebrew, pnpm, node 20+, python 3.12, uv, docker desktop.
2. clone the repo, `./scripts/bootstrap.sh`, `./scripts/setup_keys.sh`.
3. grant full disk access + automation to the launchd context (runbook).
4. `./scripts/setup_remote.sh` sets remote_secret (bearer middleware
   enforces it on every /api/* call).
5. `uv run ro up`. join the tailnet; open the web ui from your phone via
   the tailscale hostname.

note on keychain: secrets live in the mini's login keychain. run the api
as a logged-in user session (launchd agent, not daemon) so keyring works.

## option b: linux vps (no imessage, everything else)

imessage needs macos. telegram, email, voice, playbooks, triggers, mcp,
push all work. good $5/month shape.

1. a debian/ubuntu box, a `ro` user, tailscale up.
2. install: docker, pnpm, node 20+, python 3.12, uv, ffmpeg.
3. clone, bootstrap, keys. linux keyring: install `gnome-keyring` or use
   `keyrings.alt` file backend (accepting its weaker at-rest story), or
   set `postgres_url` style secrets through your own secret store.
4. `sudo cp infra/systemd/ro-*.service /etc/systemd/system/ && sudo systemctl enable --now ro-api ro-web`
5. https for web push off-localhost: `tailscale cert <host>` and put
   caddy or nginx in front with that cert.

## which one

if imessage is your main channel, the mini. if telegram is enough, the
vps is cheaper and simpler. either way the bearer token and the approval
gate are what stand between the network and ro's hands.
