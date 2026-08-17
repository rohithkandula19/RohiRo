# launch kit

everything you need to take ro public. you post it; nothing here posts
itself.

## before you post (the credibility checklist)

1. run `./scripts/go_live.sh` and use ro yourself for at least a few days.
   the first comment will be "do you actually use this?" — have a real
   answer with a real screenshot (the digest, the approval card on your
   phone, the audit page).
2. `uv run ro doctor` fully green on your machine.
3. skim the repo one last time for anything personal you don't want public
   (playbooks/ and bots/ are gitignored; check anyway).
4. pin the repo on your github profile.

## show hn draft

**title options (pick one, don't editorialize — hn hates that):**

- Show HN: Ro – a team of AI agents on your own Mac, nothing sent without your yes
- Show HN: I built an open-source, local-first alternative to Grok Bot
- Show HN: A personal agent OS where every outward byte needs your approval

**post body:**

> I spent the last months building ro, a personal agent OS that runs
> entirely on my Mac: a supervisor + 15 specialist agents, iMessage /
> Telegram / voice / web as channels, playbooks you teach in plain words,
> named bots that delegate to each other, and routines that run while I
> sleep.
>
> The part I care most about is the safety architecture, because agents
> with your inbox and your shell are terrifying:
>
> - every outward action (send, post, shell, MCP call) stops at an
>   approval card — the state machine is compare-and-swap, so nothing can
>   double-send, and edited drafts run exactly once
> - every departure is written to a hash-chained egress ledger you can
>   verify with one click
> - "vault lanes": sources you tag (a contact, your finance agent) are
>   only ever processed by local models, and the taint follows the data
>   into memory so it can never enter a cloud-bound prompt
> - airgap mode runs the whole thing offline on ollama
> - secrets only live in the macOS keychain; channels fail closed
>
> Grok Bot launched last week at $200-300/mo on a shared cloud computer
> whose own docs say not to treat bots as a security boundary. ro is my
> answer to wanting that class of product with the trust model inverted:
> my hardware, my rules, receipts.
>
> MIT licensed. Setup is one guided script (macOS; Linux mostly works,
> iMessage excepted). Would love adversarial eyes on the approval gate and
> the injection evals — SECURITY.md has the details.

## expected hard questions (have answers ready)

- "do you use it daily?" — only honest answers survive here.
- "what happens when the model is prompt-injected?" — the gate is the
  backstop; injection evals in the repo; invite them to break it.
- "why postgres for a personal tool?" — pgvector hybrid retrieval + the
  approval CAS needs a real db; compose file makes it one command.
- "another agent framework?" — it's not a framework, it's a finished
  single-user product with opinions. frameworks are the ingredient; this
  is the meal.
- "macs only?" — systemd units + substrate doc exist; imessage is
  physically mac-only (no api exists).

## where to post, in order

1. show hn (tuesday-thursday, ~9am ET historically best)
2. r/LocalLLaMA (the vault lanes + airgap story is made for them)
3. r/selfhosted
4. x/twitter thread: lead with the 15-second video of an approval card
   arriving on your phone and the audit chain verifying
5. lobste.rs if you have an invite

one channel per day; answer every comment the first 6 hours.
