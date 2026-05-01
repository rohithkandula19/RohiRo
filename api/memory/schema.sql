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
