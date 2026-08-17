# contributing

ro is a personal agent os. contributions are welcome; the bar is the same
one the codebase was built with.

## ground rules

- every outward write goes through the approval gate. no exception has ever
  been merged and none will be. if your feature needs to send something, it
  opens a card.
- secrets live in the macos keychain. a pr that reads a secret from env or
  a file will be closed.
- channels fail closed. new listeners refuse to start unconfigured.
- honest degradation over fake output: if a tool fails, say so. shaped
  stub data that passes for real data is a bug.
- lowercase docs, short sentences, no em dashes. read DECISIONS.md to hear
  the voice.

## workflow

```
uv sync --extra dev
uv run pytest tests          # 80+ tests; db tests skip without postgres
cd web && pnpm build && pnpm lint
```

- one logical change per pr, with tests for the failure mode, not just the
  happy path.
- append your reasoning to DECISIONS.md: date, choice, why. that file is
  the project's memory.
- security-sensitive surfaces (approvals, ledger, lanes, listeners) need an
  adversarial test: show the attack your change survives.

## where help is wanted

- linux support (systemd units exist; keyring backend needs love)
- more mcp server recipes in mcp_servers.example.json
- eval cases: tests/evals/*.yaml — real tasks with pass criteria
- the deferred list in TODOS.md
