# todos

deferred scope, with enough context to pick each item up cold.

## whatsapp entry point

api/integrations/whatsapp.py exists (91 lines) and stays parked. wiring it as
an entry point needs a meta business api account and webhook hosting, an
external dependency we chose not to take on in the finish-the-build plan.
when picked up: mirror the telegram poller pattern, secrets from keychain,
outward sends through the approval gate.

## screen-recording demonstration capture

grok-bot style "watch me do it once" workflow capture. deferred as a new
subsystem. v1 workflow learning ships text-taught run-verbatim playbooks
instead (see PLAN.md h.2). revisit once playbooks prove out and there is a
concrete task that text teaching cannot express.

## plaid sandbox + apple health bridges

original spec phase 5 leftovers. finance and health agents keep read-only
manual import. when picked up: plaid sandbox keys via keychain, apple health
export via the ios shortcut route.
