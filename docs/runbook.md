# runbook

what to do when a piece of ro goes red. each entry maps to a failure mode
in the registry (PLAN.md).

## imessage listener red or stale

- chat.db unreadable: system settings -> privacy -> full disk access ->
  grant to the process running the api (terminal or launchd context).
  macos updates revoke this silently.
- imessage_channel unset: `keyring set ro imessage_channel` with your own
  number, email, or the chat name. the listener refuses to start without it.
- replies not sending: automation permission for Messages.app. first send
  after a reboot pops a consent dialog; approve it.

## telegram listener red

- owner unset: `keyring set ro telegram_owner_id`. fail closed by design.
- 409 conflict: two pollers on one token. only one api instance may run.
- invalid token: rotate via botfather, update keychain.

## gmail listener red

- user_email unset: `keyring set ro user_email`.
- oauth expired: rerun scripts/setup_gmail_oauth.py.

## schedule disabled itself

- 3 consecutive failures or a broken cron spec disables a schedule and
  notifies. fix the spec or the underlying error, then re-enable from
  /settings or the schedules api.

## everything paused

- budget tripped: /settings shows spend vs cap. raise the cap in settings
  or wait for the day to roll over. background runs refuse while over.

## approvals stuck in executing

- a crash landed between the provider send and the executed mark. the row
  is intentionally not re-claimable (re-claiming could double-send).
  check the provider (did the mail/text go out?), then decide: if it went
  out, leave it; the result column is empty but the send happened once.

## push not arriving

- keys missing: `uv run python -m api.integrations.webpush --generate`.
- subscription dead: it prunes on 410 automatically; re-enable from
  /settings on the browser you want pinged.

## fresh clone will not boot

- `./scripts/bootstrap.sh` applies schema.sql and tree_schema.sql. if you
  skipped it, listeners fail on missing tables. run it once.
