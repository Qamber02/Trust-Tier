-- A failed signature may come from an unknown badge, so rejection records must
-- not require a foreign-key row in devices/workers before they can be audited.
create table if not exists public.event_rejections (
  event_id text primary key,
  device_id text not null,
  worker_id text not null,
  reason text not null,
  event_payload jsonb not null,
  created_at timestamptz not null default now()
);
alter table public.event_rejections enable row level security;
-- No client policies or grants: service role only.
