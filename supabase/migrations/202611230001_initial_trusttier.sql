-- TrustTier's Postgres-backed operational and graph model.
create extension if not exists pgcrypto;
create table if not exists public.workers (id text primary key, display_name text not null, cohort text not null default 'unclassified', active boolean not null default true, created_at timestamptz not null default now());
create table if not exists public.clients (id text primary key, display_name text not null default '', created_at timestamptz not null default now());
create table if not exists public.jobs (
  id text primary key default gen_random_uuid()::text,
  worker_id text not null references public.workers(id), client_id text not null references public.clients(id),
  title text not null, address text not null default '',
  status text not null default 'requested' check (status in ('requested','in_progress','awaiting_confirm','completed','disputed','cancelled')),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.devices (
  id text primary key, worker_id text not null references public.workers(id), public_key text not null,
  algorithm text not null default 'ed25519' check (algorithm in ('ed25519','ecdsa-p256')),
  last_seen_at timestamptz, last_hash text, created_at timestamptz not null default now()
);
create table if not exists public.events (
  id text primary key, device_id text not null references public.devices(id),
  worker_id text not null references public.workers(id), job_id text references public.jobs(id),
  client_id text references public.clients(id), type text not null check (type in ('arrive','start','finish')),
  evidence_tier text not null check (evidence_tier in ('self','nfc','signed')),
  device_ts timestamptz not null, payload jsonb not null default '{}'::jsonb, signature text not null,
  prev_hash text not null default '', hash text not null, verified boolean not null default false,
  rejection_reason text, synced_at timestamptz not null default now(), unique(device_id, hash)
);
create index if not exists events_worker_time_idx on public.events(worker_id, device_ts desc);
create index if not exists events_job_time_idx on public.events(job_id, device_ts);
create index if not exists events_device_chain_idx on public.events(device_id, hash);
create table if not exists public.payments (
  id uuid primary key default gen_random_uuid(), job_id text not null references public.jobs(id),
  worker_id text not null references public.workers(id), amount numeric(12,2) not null check (amount >= 0),
  currency text not null default 'PKR', status text not null default 'pending' check (status in ('pending','released','held','refunded')),
  created_at timestamptz not null default now()
);
create table if not exists public.reviews (
  id uuid primary key default gen_random_uuid(), job_id text not null references public.jobs(id),
  worker_id text not null references public.workers(id), client_id text not null references public.clients(id),
  stars smallint not null check (stars between 1 and 5), body text not null default '', sentiment numeric(4,3),
  created_at timestamptz not null default now(), unique(job_id, client_id)
);
create table if not exists public.disputes (
  id uuid primary key default gen_random_uuid(), job_id text not null references public.jobs(id),
  worker_id text not null references public.workers(id), client_id text not null references public.clients(id),
  reason text not null, status text not null default 'open' check (status in ('open','investigating','resolved','rejected')),
  created_at timestamptz not null default now()
);
create table if not exists public.trust_scores (
  worker_id text primary key references public.workers(id), score double precision not null default 0.6209 check (score between 0 and 1),
  evidence_counts jsonb not null default '{"self":0,"nfc":0,"signed":0}'::jsonb, updated_at timestamptz not null default now()
);
create table if not exists public.trust_score_history (
  id bigint generated always as identity primary key, worker_id text not null references public.workers(id),
  event_id text references public.events(id), previous_score double precision not null, score double precision not null,
  evidence_tier text not null check (evidence_tier in ('self','nfc','signed')), created_at timestamptz not null default now()
);
create index if not exists trust_history_worker_time_idx on public.trust_score_history(worker_id, created_at desc);
create table if not exists public.edges (
  id bigint generated always as identity primary key, src_id text not null, dst_id text not null,
  type text not null, weight double precision not null default 1 check (weight >= 0 and weight <= 1),
  created_at timestamptz not null default now(), unique(src_id, dst_id, type)
);
create index if not exists edges_src_type_idx on public.edges(src_id, type);
create index if not exists edges_dst_type_idx on public.edges(dst_id, type);

-- Indexed adjacency table traversal, capped at five hops.
create or replace function public.traverse_edges(start_id text, max_depth integer default 3)
returns table(node_id text, depth integer, path text[])
language sql stable security invoker set search_path = public as $$
  with recursive walk(node_id, depth, path) as (
    select start_id, 0, array[start_id]
    union all
    select e.dst_id, w.depth + 1, w.path || e.dst_id from walk w join public.edges e on e.src_id = w.node_id
    where w.depth < least(greatest(max_depth, 0), 5) and not e.dst_id = any(w.path)
  ) select node_id, depth, path from walk;
$$;

alter table public.workers enable row level security;
alter table public.clients enable row level security;
alter table public.jobs enable row level security;
alter table public.devices enable row level security;
alter table public.events enable row level security;
alter table public.payments enable row level security;
alter table public.reviews enable row level security;
alter table public.disputes enable row level security;
alter table public.trust_scores enable row level security;
alter table public.trust_score_history enable row level security;
alter table public.edges enable row level security;

-- Authenticated app users get only appropriate read access. Mutations remain server-side.
create policy workers_read_authenticated on public.workers for select to authenticated using (true);
create policy clients_self_read on public.clients for select to authenticated using (id = auth.uid()::text);
create policy jobs_party_read on public.jobs for select to authenticated using (worker_id = auth.uid()::text or client_id = auth.uid()::text);
create policy events_worker_read on public.events for select to authenticated using (worker_id = auth.uid()::text and verified = true);
create policy trust_scores_read_authenticated on public.trust_scores for select to authenticated using (true);
create policy trust_history_read_authenticated on public.trust_score_history for select to authenticated using (true);
create policy reviews_read_authenticated on public.reviews for select to authenticated using (true);
create policy disputes_party_read on public.disputes for select to authenticated using (worker_id = auth.uid()::text or client_id = auth.uid()::text);
create policy edges_read_authenticated on public.edges for select to authenticated using (true);
create policy payments_worker_read on public.payments for select to authenticated using (worker_id = auth.uid()::text);
grant select on public.workers, public.trust_scores, public.trust_score_history, public.reviews, public.jobs, public.events, public.disputes, public.payments, public.edges to authenticated;

do $$ begin alter publication supabase_realtime add table public.events; exception when duplicate_object then null; end $$;
do $$ begin alter publication supabase_realtime add table public.trust_scores; exception when duplicate_object then null; end $$;
do $$ begin alter publication supabase_realtime add table public.disputes; exception when duplicate_object then null; end $$;
do $$ begin alter publication supabase_realtime add table public.reviews; exception when duplicate_object then null; end $$;
