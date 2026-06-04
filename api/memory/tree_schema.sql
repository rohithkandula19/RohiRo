-- memory tree schema
-- a hierarchical time-based summary tree. inspired by openhuman's tree_summarizer.
--
-- raw_events: every act ro takes or observes (emails seen, meetings booked,
-- drafts approved, repos pulled). a stream.
--
-- tree_nodes: hierarchical roll-ups. path is "/yyyy/mm/dd/hh" with depth 1-4.
--   /             root (depth 0)
--   /2026         year
--   /2026/05      month
--   /2026/05/13   day
--   /2026/05/13/14 hour-leaf
--
-- the summarizer:
--   1. finds hour-leaves whose buffered raw_events are unsummarized
--   2. summarizes that hour into markdown via claude
--   3. marks events as summarized
--   4. walks up the path, re-summarizing each ancestor from its now-fresh children

create table if not exists raw_events (
    id uuid primary key default gen_random_uuid(),
    happened_at timestamptz not null default now(),
    source text not null,        -- gmail, calendar, github, slack, imessage, chat, action
    kind text not null,          -- email_read, email_drafted, email_sent, meeting_booked, draft_approved, ...
    actor text not null default 'ro',  -- ro | user | external
    summary text not null,        -- one-line human-readable description
    payload jsonb not null default '{}'::jsonb,
    summarized_at timestamptz    -- null = pending roll-up
);
create index if not exists raw_events_pending_idx on raw_events (happened_at) where summarized_at is null;
create index if not exists raw_events_source_idx on raw_events (source, happened_at desc);
create index if not exists raw_events_kind_idx on raw_events (kind, happened_at desc);

create table if not exists tree_nodes (
    path text primary key,        -- /yyyy/mm/dd/hh or any prefix
    depth integer not null,       -- 0..4
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    summary_md text not null default '',
    title text not null default '',  -- human label (e.g. "May 13", "2pm hour")
    event_count integer not null default 0,
    children_dirty boolean not null default false,  -- a descendant changed; needs re-summary
    updated_at timestamptz not null default now()
);
create index if not exists tree_nodes_depth_idx on tree_nodes (depth);
create index if not exists tree_nodes_dirty_idx on tree_nodes (children_dirty) where children_dirty;
create index if not exists tree_nodes_summary_trgm on tree_nodes using gin (summary_md gin_trgm_ops);

-- helper view: pending hour-leaves (events to fold up next)
create or replace view pending_hours as
select
    to_char(happened_at at time zone 'utc', '/YYYY/MM/DD/HH24') as path,
    count(*) as event_count,
    min(happened_at) as starts_at,
    max(happened_at) as latest_at
from raw_events
where summarized_at is null
group by 1;
