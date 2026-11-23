-- Separate the rider's workflow actions from customer decisions and signed badge events.
create table if not exists public.job_activity (
  id bigint generated always as identity primary key,
  job_id text not null references public.jobs(id) on delete cascade,
  actor_role text not null check (actor_role in ('rider','customer','system')),
  actor_id text not null,
  action text not null check (action in (
    'requested','accepted','declined','arrived','started','finished',
    'confirmed','disputed','cancelled'
  )),
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists job_activity_job_time_idx
  on public.job_activity(job_id, created_at desc);
create index if not exists job_activity_actor_time_idx
  on public.job_activity(actor_role, actor_id, created_at desc);
create index if not exists jobs_worker_status_updated_idx
  on public.jobs(worker_id, status, updated_at desc);
create index if not exists jobs_client_updated_idx
  on public.jobs(client_id, updated_at desc);

alter table public.job_activity enable row level security;
create policy job_activity_party_read on public.job_activity for select to authenticated
  using (exists (
    select 1 from public.jobs j
    where j.id = job_activity.job_id
      and (j.worker_id = auth.uid()::text or j.client_id = auth.uid()::text)
  ));
grant select on public.job_activity to authenticated;
do $$ begin
  alter publication supabase_realtime add table public.job_activity;
exception when duplicate_object then null;
end $$;
