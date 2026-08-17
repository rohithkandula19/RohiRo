# playbooks

teach ro a task once, run it forever. each .md file here is a playbook.

- the whole file is the instruction. plain markdown.
- add `## step` headings to make it a chain: steps run in order, each one
  seeing a digest of the previous step's output.
- schedule one: create a schedule whose text is `playbook:<name>`.
- run one now: POST /api/playbooks/<name>/run, or ask ro in chat.
- outward writes inside a playbook hit the same approval gate as
  everything else. playbooks cannot bypass it.

example (save as morning-scan.md):

    # morning scan
    ## step research
    check my calendar for today and summarize what matters.
    ## step brief
    using the context above, write me a two paragraph morning brief.
