-- 009_grid_heat_inputs.sql
-- 1. Grid conditions: how bad NEPA supply is in each city, by date (the simulator uses these).
-- 2. Customer inputs: uploaded receipts / voice notes / photos, their own prices, their appliances.

-- ---------- 1. grid conditions ----------
create table public.grid_conditions (
  id             bigint generated always as identity primary key,
  city           text not null,
  starts         date not null,
  ends           date,                                   -- null = still going on
  hours_per_day  real not null check (hours_per_day between 0 and 24),
  mean_outage_h  real not null check (mean_outage_h > 0),
  note           text,
  created_at     timestamptz not null default now()
);
alter table public.grid_conditions enable row level security;
create policy "read grid conditions" on public.grid_conditions for select to authenticated using (true);

-- Assumptions from news reports (Oct 2026). Edit with: python -m scripts.set_grid
insert into public.grid_conditions (city, starts, ends, hours_per_day, mean_outage_h, note) values
  ('Lagos',         '2026-10-10', null,         6.0,  6.0, 'Grid allocation shortfall: gas shortages, plants offline, line trips'),
  ('Lagos',         '2026-10-18', '2026-10-21', 1.5, 14.0, 'Generation crashed to under 500 MW (19 Oct)'),
  ('Port Harcourt', '2026-10-12', null,         8.0,  4.0, 'Poor supply; Alaoji-Afam line outage'),
  ('Port Harcourt', '2026-10-19', '2026-10-20', 2.0, 12.0, 'National generation crash');

-- ---------- 2. customer inputs ----------
-- Every file a customer or technician adds, and what Gemini read from it.
create table public.uploads (
  id            uuid primary key default gen_random_uuid(),
  site_id       uuid not null references public.sites (id) on delete cascade,
  uploaded_by   uuid references public.profiles (id) on delete set null,
  kind          text not null check (kind in ('token_receipt', 'fuel_receipt', 'voice_note', 'photo')),
  component     text,                                    -- photos: inverter, battery, panels, ...
  storage_path  text not null,
  mime_type     text not null,
  status        text not null default 'pending' check (status in ('pending', 'read', 'failed')),
  extracted     jsonb not null default '{}',
  error         text,
  created_at    timestamptz not null default now()
);
create index uploads_site_idx on public.uploads (site_id, created_at desc);

-- A site's own prices (from receipts or the fuel form); these beat the city-wide prices table.
create table public.site_prices (
  id              bigint generated always as identity primary key,
  site_id         uuid not null references public.sites (id) on delete cascade,
  item            text not null check (item in ('grid', 'petrol', 'diesel')),
  price_ngn       numeric(10, 2) not null check (price_ngn > 0),   -- per kWh (grid) or per litre
  effective_from  date not null,
  source          text,
  upload_id       uuid references public.uploads (id) on delete set null,
  created_at      timestamptz not null default now()
);
create index site_prices_idx on public.site_prices (site_id, item, effective_from desc);

-- The appliances a customer says they own (used by "Can I use...?" and the live picture).
create table public.site_appliances (
  site_id  uuid not null references public.sites (id) on delete cascade,
  name     text not null,
  watts    real not null check (watts > 0),
  qty      integer not null default 1 check (qty > 0),
  primary key (site_id, name)
);

alter table public.uploads         enable row level security;
alter table public.site_prices     enable row level security;
alter table public.site_appliances enable row level security;
create policy "read uploads"         on public.uploads         for select to authenticated using (public.can_view_site(site_id));
create policy "read site prices"     on public.site_prices     for select to authenticated using (public.can_view_site(site_id));
create policy "read site appliances" on public.site_appliances for select to authenticated using (public.can_view_site(site_id));
-- All writes go through the backend (service role), which checks who is allowed.

-- Private file storage for uploads (only the backend reads and writes it).
insert into storage.buckets (id, name, public) values ('uploads', 'uploads', false)
on conflict (id) do nothing;
