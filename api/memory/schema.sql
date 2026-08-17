-- ro memory schema
-- one user. all about ro.
-- profile is a singleton. everything else hangs off it.

create extension if not exists vector;
create extension if not exists pg_trgm;

-- profile is markdown. one row, always id=1. the source of truth.
create table if not exists profile (
    id integer primary key default 1,
    body text not null default '',
    updated_at timestamptz not null default now(),
    constraint profile_singleton check (id = 1)
);
insert into profile (id, body) values (1, '') on conflict do nothing;

-- contacts are people ro knows.
create table if not exists contacts (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    email text,
    phone text,
    handles jsonb not null default '{}'::jsonb,  -- {slack, telegram, github, etc}
    role text,
    company text,
    notes text,
    last_interaction_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists contacts_email_idx on contacts (lower(email));
create index if not exists contacts_name_trgm on contacts using gin (name gin_trgm_ops);

-- projects ro is working on or watching.
create table if not exists projects (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    status text not null default 'active',  -- active, paused, done, archived
    summary text,
    repo_url text,
    links jsonb not null default '[]'::jsonb,
    blockers text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- tasks are things to do. across domains.
create table if not exists tasks (
    id uuid primary key default gen_random_uuid(),
    title text not null,
    body text,
    domain text not null,  -- comms, code, jobs, admin, etc
    status text not null default 'open',  -- open, in_progress, done, dropped
    due_at timestamptz,
    project_id uuid references projects(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists tasks_status_idx on tasks (status);
create index if not exists tasks_domain_idx on tasks (domain);

-- decisions are the why. immutable log.
create table if not exists decisions (
    id uuid primary key default gen_random_uuid(),
    title text not null,
    body text not null,
    decided_at timestamptz not null default now(),
    tags text[] not null default '{}'
);
create index if not exists decisions_tags_idx on decisions using gin (tags);

-- conversations: every exchange with the supervisor.
create table if not exists conversations (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null,
    role text not null,  -- user, assistant, tool
    body text not null,
    body_tsv tsvector generated always as (to_tsvector('english', body)) stored,
    embedding vector(1536),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
create index if not exists conversations_session_idx on conversations (session_id, created_at);
create index if not exists conversations_tsv_idx on conversations using gin (body_tsv);
create index if not exists conversations_embedding_idx
    on conversations using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- entities: things mentioned often. people, products, code symbols.
-- the consolidator promotes these from raw conversations.
create table if not exists entities (
    id uuid primary key default gen_random_uuid(),
    kind text not null,  -- person, project, paper, repo, place
    name text not null,
    summary text,
    embedding vector(1536),
    last_seen_at timestamptz not null default now(),
    seen_count integer not null default 1,
    metadata jsonb not null default '{}'::jsonb,
    unique (kind, name)
);
create index if not exists entities_kind_idx on entities (kind);
create index if not exists entities_embedding_idx
    on entities using ivfflat (embedding vector_cosine_ops) with (lists = 50);

-- events: things that happened. emails sent, meetings held, deploys shipped.
-- a stream, not state.
create table if not exists events (
    id uuid primary key default gen_random_uuid(),
    kind text not null,  -- email_sent, meeting_held, pr_merged, etc
    body jsonb not null,
    happened_at timestamptz not null default now()
);
create index if not exists events_kind_at_idx on events (kind, happened_at desc);

-- preferences: small key/value tweaks. tone, default model, etc.
create table if not exists preferences (
    key text primary key,
    value jsonb not null,
    updated_at timestamptz not null default now()
);

-- action_log: every outward write. supervisor pauses on these.
create table if not exists action_log (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null,
    domain text not null,
    tool text not null,
    description text not null,
    payload jsonb not null,
    requires_approval boolean not null default true,
    status text not null default 'pending',  -- pending, approved, rejected, edited, executed, failed
    edit_note text,
    created_at timestamptz not null default now(),
    decided_at timestamptz,
    executed_at timestamptz,
    error text
);
create index if not exists action_log_status_idx on action_log (status, created_at);
create index if not exists action_log_session_idx on action_log (session_id);

-- provider result of an executed action (message id etc). additive.
alter table action_log add column if not exists result jsonb;

-- seen_keys: dedupe + watermarks for listeners and autofetch.
-- (source, external_id) is the identity; on conflict do nothing depends on it.
create table if not exists seen_keys (
    source text not null,
    external_id text not null,
    first_seen_at timestamptz not null default now(),
    primary key (source, external_id)
);

-- schedules: cron and one-shot routines the scheduler engine fires.
create table if not exists schedules (
    id uuid primary key default gen_random_uuid(),
    kind text not null,                    -- cron | once
    spec text not null,
    text text not null,
    title text not null default '',
    timezone text not null default 'UTC',
    enabled boolean not null default true,
    last_run_at timestamptz,
    next_run_at timestamptz not null,
    last_result text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists schedules_due_idx on schedules (enabled, next_run_at);

-- consecutive failure counter. scheduler disables a schedule at 3.
alter table schedules add column if not exists consecutive_failures integer not null default 0;

-- vault taint: rows born in a vault lane never enter cloud-bound prompts.
alter table conversations add column if not exists vault boolean not null default false;

-- archive_messages: total recall. lifetime corpus, no retention limits.
create table if not exists archive_messages (
    id bigint generated always as identity primary key,
    source text not null,               -- imessage | gmail | conversation
    external_id text not null,          -- rowid / message id / conversation uuid
    contact_key text not null default '',  -- handle or email of the counterparty
    sender text not null default '',
    from_me boolean not null default false,
    body text not null,
    body_tsv tsvector generated always as (to_tsvector('english', body)) stored,
    vault boolean not null default false,
    sent_at timestamptz,
    archived_at timestamptz not null default now(),
    unique (source, external_id)
);
create index if not exists archive_tsv_idx on archive_messages using gin (body_tsv);
create index if not exists archive_contact_idx on archive_messages (contact_key, sent_at);

-- commitments: open loops mined from sent messages, both directions.
create table if not exists commitments (
    id uuid primary key default gen_random_uuid(),
    direction text not null,            -- mine | theirs
    who text not null default '',
    what text not null,
    due_hint text not null default '',
    source text not null default '',    -- imessage | gmail
    source_ref text not null default '',
    status text not null default 'open',  -- open | done | dropped
    created_at timestamptz not null default now(),
    resolved_at timestamptz
);
create index if not exists commitments_status_idx on commitments (status, created_at);

-- egress_ledger: hash-chained record of every outward byte.
create table if not exists egress_ledger (
    id bigint generated always as identity primary key,
    prev_hash text not null,
    hash text not null,
    action_id uuid,                     -- null for self-channel replies
    basis text not null,                -- approval | self-channel | digest
    channel text not null,
    destination text not null default '',
    payload_sha text not null,
    created_at timestamptz not null default now()
);

-- contact_dossiers: the relationship register.
create table if not exists contact_dossiers (
    contact_key text primary key,
    display_name text not null default '',
    dossier_md text not null default '',
    sources jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

-- learned_voice: per-channel tone rules derived from your edits.
create table if not exists learned_voice (
    channel text primary key,
    rules_md text not null default '',
    n_signals integer not null default 0,
    updated_at timestamptz not null default now()
);

-- voice_signals: raw approve/edit/reject signals the voice learner reads.
create table if not exists voice_signals (
    id uuid primary key default gen_random_uuid(),
    action_id uuid not null,
    tool text not null default '',
    channel text not null,
    decision text not null,
    original text not null default '',
    edited text not null default '',
    created_at timestamptz not null default now()
);
create index if not exists voice_signals_channel_idx on voice_signals (channel, created_at);

-- bot_messages: every handoff between crew bots, logged. no hidden channels.
create table if not exists bot_messages (
    id bigint generated always as identity primary key,
    from_bot text not null,
    to_bot text not null,
    body text not null,
    created_at timestamptz not null default now()
);
create index if not exists bot_messages_time_idx on bot_messages (created_at);

-- triggers: when an inbound event matches, run a playbook.
create table if not exists triggers (
    id uuid primary key default gen_random_uuid(),
    channel text not null default '*',      -- imessage | telegram | email | whatsapp | *
    pattern text not null,                  -- case-insensitive substring or /regex/
    playbook text not null,                 -- playbook name to run
    enabled boolean not null default true,
    last_fired_at timestamptz,
    fire_count integer not null default 0,
    created_at timestamptz not null default now()
);

-- push_subscriptions: web push targets for the localhost ui.
create table if not exists push_subscriptions (
    endpoint text primary key,
    subscription jsonb not null,
    created_at timestamptz not null default now()
);

-- heartbeats: one row per background worker / integration, latest state.
create table if not exists heartbeats (
    name text primary key,
    ok boolean not null default true,
    error text not null default '',
    beat_at timestamptz not null default now()
);

-- spend_log: one row per claude call, attributed to the run that caused it.
create table if not exists spend_log (
    id bigint generated always as identity primary key,
    run_label text not null default 'chat',
    model text not null default '',
    input_tokens integer not null default 0,
    output_tokens integer not null default 0,
    created_at timestamptz not null default now()
);
create index if not exists spend_log_day_idx on spend_log (created_at);

-- stable session per chat channel so conversations keep context.
create table if not exists channel_sessions (
    channel text not null,                 -- imessage | telegram | email | whatsapp
    chat_key text not null,                -- chat guid / chat_id / thread key
    session_id uuid not null default gen_random_uuid(),
    created_at timestamptz not null default now(),
    primary key (channel, chat_key)
);

-- the trigger that keeps updated_at fresh.
create or replace function touch_updated_at() returns trigger as $$
begin
    new.updated_at := now();
    return new;
end;
$$ language plpgsql;

do $$
begin
    if not exists (select 1 from pg_trigger where tgname = 'touch_profile') then
        create trigger touch_profile before update on profile for each row execute function touch_updated_at();
    end if;
    if not exists (select 1 from pg_trigger where tgname = 'touch_contacts') then
        create trigger touch_contacts before update on contacts for each row execute function touch_updated_at();
    end if;
    if not exists (select 1 from pg_trigger where tgname = 'touch_projects') then
        create trigger touch_projects before update on projects for each row execute function touch_updated_at();
    end if;
    if not exists (select 1 from pg_trigger where tgname = 'touch_tasks') then
        create trigger touch_tasks before update on tasks for each row execute function touch_updated_at();
    end if;
end$$;
