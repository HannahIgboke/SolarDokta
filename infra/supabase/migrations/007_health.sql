-- 007_health.sql
-- Long-term health numbers. Raw 5-minute telemetry is only kept for 30 days, but some detectors
-- need months: dust compares against the site's usual clean level, and battery fade needs a
-- 4-month trend. So each day we keep a few small numbers per site, forever.

-- One row per site per day.
create table public.health_daily (
  site_id       uuid not null references public.sites (id) on delete cascade,
  day           date not null,
  pr_pv1        real,            -- performance ratio of string 1: actual / expected solar
  pr_pv2        real,            -- (only measured while no solar was being thrown away)
  usable_steps  integer,         -- how many 5-minute steps that measurement used
  batt_heat_c   real,            -- battery temperature minus outdoor temperature, daily mean
  primary key (site_id, day)
);

-- One row per deep discharge: the battery's estimated health (usable / nameplate capacity).
create table public.battery_estimates (
  site_id       uuid not null references public.sites (id) on delete cascade,
  ts            timestamptz not null,   -- when the discharge ended
  soh_estimate  real not null,
  primary key (site_id, ts)
);

alter table public.health_daily      enable row level security;
alter table public.battery_estimates enable row level security;
create policy "read health daily"      on public.health_daily      for select to authenticated
  using (public.can_view_site(site_id));
create policy "read battery estimates" on public.battery_estimates for select to authenticated
  using (public.can_view_site(site_id));

-- Fast lookups of a site's open findings (the detector job checks these every hour).
create index if not exists findings_site_status_idx on public.findings (site_id, status);
