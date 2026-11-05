-- 011_push.sql
-- Phone notifications (Web Push): one row per browser/phone that turned alerts on.
-- Only the backend reads or writes this table (RLS on, no policies).

create table if not exists public.push_subscriptions (
  id          text primary key,                 -- hash of the endpoint
  endpoint    text not null unique,
  p256dh      text not null,
  auth        text not null,
  lang        text not null default 'en' check (lang in ('en', 'pcm', 'ig')),
  role        text not null check (role in ('customer', 'staff')),
  profile_id  uuid references public.profiles (id) on delete cascade,   -- null for demo visitors
  org_id      uuid references public.organisations (id) on delete cascade,
  site_id     uuid references public.sites (id) on delete cascade,      -- customers: their site
  demo        boolean not null default false,
  created_at  timestamptz not null default now()
);
create index if not exists push_subscriptions_site_idx on public.push_subscriptions (site_id);
alter table public.push_subscriptions enable row level security;

-- alerts can now go out as phone notifications too
alter table public.alerts drop constraint if exists alerts_channel_check;
alter table public.alerts add constraint alerts_channel_check
  check (channel in ('whatsapp', 'sms', 'email', 'push'));
