"""real third-party integrations.

each module is a small async client around a vendor api. they share the same
shape: configured() check, a few high-level verbs (search, fetch, draft, send),
and structured return types the agents can hand to the ui.
"""
