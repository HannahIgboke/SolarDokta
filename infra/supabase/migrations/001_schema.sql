-- 001_schema.sql
-- SolarDokta core tables. Run once in the Supabase SQL editor.

-- ---------- Organisations and people ----------
create table public.organisations (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  created_at  timestamptz not null default now()
);

-- One profile per login. "staff" = installer admin/technician side, "customer" = system owner.
create table public.profiles (
  id                  uuid primary key references auth.users (id) on delete cascade,
  org_id              uuid not null references public.organisations (id) on delete cascade,
  role                text not null check (role in ('staff', 'customer')),
  full_name           text,
  whatsapp_number     text,                       -- E.164 format, e.g. +2348012345678
  preferred_language  text not null default 'en' check (preferred_language in ('en', 'pcm')),
  created_at          timestamptz not null default now()
);

-- ---------- Sites (one solar system each) ----------
create table public.sites (
  id                       uuid primary key default gen_random_uuid(),
  code                     text not null unique,  -- short readable id, e.g. 'lagos-001'
  org_id                   uuid not null references public.organisations (id) on delete cascade,
  customer_id              uuid references public.profiles (id) on delete set null,
  name                     text not null,
  city                     text not null,
  latitude                 numeric(8, 5) not null,
  longitude                numeric(8, 5) not null,
  timezone                 text not null default 'Africa/Lagos',
  pv1_kwp                  numeric(6, 2) not null,
  pv2_kwp                  numeric(6, 2) not null default 0,
  tilt_deg                 numeric(4, 1) not null default 10,
  azimuth_deg              numeric(5, 1) not null default 180,  -- 180 = facing south
  inverter_kw              numeric(6, 2) not null,
  battery_kwh              numeric(6, 2) not null,
  battery_chemistry        text not null check (battery_chemistry in ('lifepo4', 'lead_acid')),
  tariff_band              text not null check (tariff_band in ('A', 'B', 'C', 'D', 'E')),
  generator_fuel           text not null default 'petrol' check (generator_fuel in ('petrol', 'diesel', 'none')),
  generator_kwh_per_litre  numeric(4, 2) not null default 1.5,  -- assumption, editable per site
  install_date             date,
  is_simulated             boolean not null default true,
  created_at               timestamptz not null default now()
);
create index sites_org_idx on public.sites (org_id);
create index sites_customer_idx on public.sites (customer_id);

-- ---------- Telemetry (5-minute readings) ----------
-- Sign convention: batt_a > 0 = charging, < 0 = discharging; grid_w > 0 = importing from grid.
create table public.telemetry (
  site_id      uuid not null references public.sites (id) on delete cascade,
  ts           timestamptz not null,
  pv1_w        real not null default 0,
  pv2_w        real not null default 0,
  pv_v         real,
  batt_soc     real check (batt_soc between 0 and 1),
  batt_v       real,
  batt_a       real,
  batt_w       real generated always as (batt_v * batt_a) stored,
  batt_temp_c  real,
  load_w       real not null default 0,
  grid_v       real not null default 0,
  grid_w       real not null default 0,
  inv_temp_c   real,
  fault_code   text,
  source       text not null default 'simulator' check (source in ('simulator', 'device', 'import')),
  primary key (site_id, ts)
);
create index telemetry_ts_idx on public.telemetry (ts);

-- Summaries kept long-term after raw readings are purged.
create table public.telemetry_hourly (
  site_id            uuid not null references public.sites (id) on delete cascade,
  hour_ts            timestamptz not null,
  pv_kwh             real not null,
  load_kwh           real not null,
  grid_import_kwh    real not null,
  batt_charge_kwh    real not null,
  batt_discharge_kwh real not null,
  soc_min            real,
  soc_max            real,
  soc_avg            real,
  batt_temp_max      real,
  grid_on_minutes    integer not null,
  samples            integer not null,
  primary key (site_id, hour_ts)
);

create table public.telemetry_daily (
  site_id            uuid not null references public.sites (id) on delete cascade,
  day                date not null,
  pv_kwh             real not null,
  load_kwh           real not null,
  grid_import_kwh    real not null,
  batt_charge_kwh    real not null,
  batt_discharge_kwh real not null,
  soc_min            real,
  soc_max            real,
  batt_temp_max      real,
  grid_on_minutes    integer not null,
  samples            integer not null,
  primary key (site_id, day)
);

-- ---------- Virtual inverter memory (so each tick continues where the last stopped) ----------
create table public.simulator_state (
  site_id     uuid primary key references public.sites (id) on delete cascade,
  last_ts     timestamptz not null,
  state       jsonb not null,
  updated_at  timestamptz not null default now()
);

-- ---------- External data ----------
create table public.weather_history (
  latitude     numeric(6, 3) not null,
  longitude    numeric(6, 3) not null,
  ts           timestamptz not null,       -- hourly, UTC
  ghi_wm2      real,                       -- sunlight on flat ground (W/m2)
  temp_c       real,
  source       text not null default 'nasa_power',
  primary key (latitude, longitude, ts)
);

create table public.weather_forecast (
  latitude         numeric(6, 3) not null,
  longitude        numeric(6, 3) not null,
  ts               timestamptz not null,
  ghi_wm2          real,
  temp_c           real,
  cloud_cover_pct  real,
  fetched_at       timestamptz not null default now(),
  source           text not null default 'open_meteo',
  primary key (latitude, longitude, ts)
);

create table public.prices (
  item            text not null check (item in ('petrol', 'diesel', 'grid_band_a', 'grid_band_b',
                                                 'grid_band_c', 'grid_band_d', 'grid_band_e')),
  unit            text not null check (unit in ('ngn_per_litre', 'ngn_per_kwh')),
  price_ngn       numeric(10, 2) not null check (price_ngn > 0),
  effective_from  date not null,
  source          text,
  primary key (item, effective_from)
);

-- ---------- What SolarDokta finds and says ----------
create table public.findings (
  id           uuid primary key default gen_random_uuid(),
  site_id      uuid not null references public.sites (id) on delete cascade,
  kind         text not null,      -- e.g. 'soiling', 'inverter_trip', 'battery_fade', 'underrated_panel'
  severity     text not null check (severity in ('info', 'warning', 'critical')),
  score        real,
  details      jsonb not null default '{}',
  status       text not null default 'open' check (status in ('open', 'resolved', 'dismissed')),
  dedupe_key   text not null,      -- stops the same problem being reported twice
  ts_start     timestamptz not null,
  ts_end       timestamptz,
  created_at   timestamptz not null default now()
);
create unique index findings_open_dedupe_idx on public.findings (site_id, dedupe_key) where status = 'open';
create index findings_site_idx on public.findings (site_id, created_at desc);

create table public.battery_cycles (
  id           bigint generated always as identity primary key,
  site_id      uuid not null references public.sites (id) on delete cascade,
  start_ts     timestamptz not null,
  end_ts       timestamptz not null,
  depth        real not null check (depth between 0 and 1),   -- depth of discharge
  avg_temp_c   real,
  max_temp_c   real,
  energy_kwh   real
);
create index battery_cycles_site_idx on public.battery_cycles (site_id, start_ts);

create table public.alerts (
  id                   uuid primary key default gen_random_uuid(),
  site_id              uuid not null references public.sites (id) on delete cascade,
  finding_id           uuid references public.findings (id) on delete set null,
  channel              text not null default 'whatsapp' check (channel in ('whatsapp', 'sms', 'email')),
  recipient            text not null,
  template             text,
  body                 text not null,
  status               text not null default 'queued'
                       check (status in ('queued', 'sent', 'delivered', 'read', 'failed')),
  provider_message_id  text,
  sent_at              timestamptz,
  created_at           timestamptz not null default now()
);
create index alerts_site_idx on public.alerts (site_id, created_at desc);

create table public.conversations (
  id            uuid primary key default gen_random_uuid(),
  site_id       uuid references public.sites (id) on delete set null,
  profile_id    uuid references public.profiles (id) on delete set null,
  phone         text not null,
  direction     text not null check (direction in ('in', 'out')),
  message_type  text not null check (message_type in ('text', 'voice', 'template')),
  content       text not null,
  tool_calls    jsonb,
  created_at    timestamptz not null default now()
);
create index conversations_phone_idx on public.conversations (phone, created_at desc);

-- Ground-truth labels for evaluation: every fault the virtual inverter injects.
create table public.injected_faults (
  id          bigint generated always as identity primary key,
  site_id     uuid not null references public.sites (id) on delete cascade,
  kind        text not null,
  params      jsonb not null default '{}',
  start_ts    timestamptz not null,
  end_ts      timestamptz,
  created_at  timestamptz not null default now()
);
