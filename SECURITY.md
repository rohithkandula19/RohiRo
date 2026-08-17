# security

ro's whole premise is that a personal agent must be safe to trust with your
life. the load-bearing claims and how to check them:

- **nothing sent without approval.** every outward write (mail, texts,
  posts, shell, mcp calls) passes a compare-and-swap approval state machine
  (api/supervisor/approval.py, execute.py) and lands in a hash-chained
  egress ledger. verify: GET /api/audit/verify recomputes the chain.
- **secrets never leave the keychain.** grep the repo: no secret is read
  from env or file. exports (`ro export`) exclude secrets by construction.
- **channels fail closed.** unconfigured listeners refuse to start rather
  than guess who may command the agent.
- **vault lanes.** content tagged vault is processed on-device only; the
  taint follows it into memory. enforcement is in the model-client choke
  points, not in prompts.
- **prompt injection.** inbound content is treated as untrusted; the eval
  suite includes direct-override, social-engineering, and fake-tool-call
  attacks (tests/evals/test_injection.py). the gate is the backstop: even a
  fooled model cannot send without a human yes.

## reporting

found a way around the gate, the lanes, or the ledger? please report it
privately first: open a github security advisory on this repo (preferred),
or email the maintainer. give us a reasonable window before disclosure.
adversarial findings with a reproducing test are the most valuable thing
you can send.

## honest limits

- the ledger proves integrity, not provenance against an attacker with
  local root. your mac's security is the floor.
- approval fatigue is a real attack: the trust-tier and structural-
  constraint features exist to keep cards rare enough to read.
- imessage and applescript surfaces depend on macos permissions that os
  updates can silently revoke; liveness turns red when that happens.
