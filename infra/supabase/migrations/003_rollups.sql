-- 003_rollups.sql
-- Summarise 5-minute readings into hourly and daily rows, and purge old raw data.
-- Energy (kWh) = power (W) x 5/60 hours / 1000 for each 5-minute reading.

create or replace function public.rollup_hourly(p_from timestamptz, p_to timestamptz)
returns integer language plpgsql security definer set search_path = public as $$
declare n integer;
begin
  insert into public.telemetry_hourly as h (
    site_id, hour_ts, pv_kwh, load_kwh, grid_import_kwh, batt_charge_kwh, batt_discharge_kwh,
    soc_min, soc_max, soc_avg, batt_temp_max, grid_on_minutes, samples)
  select
    site_id,
    date_trunc('hour', ts),
    sum(pv1_w + pv2_w)                        * (5.0 / 60) / 1000,
    sum(load_w)                               * (5.0 / 60) / 1000,
    sum(greatest(grid_w, 0))                  * (5.0 / 60) / 1000,
    sum(greatest(coalesce(batt_w, 0), 0))     * (5.0 / 60) / 1000,
    sum(greatest(-coalesce(batt_w, 0), 0))    * (5.0 / 60) / 1000,
    min(batt_soc), max(batt_soc), avg(batt_soc),
    max(batt_temp_c),
    (count(*) filter (where grid_v > 150)) * 5,
    count(*)
  from public.telemetry
  where ts >= date_trunc('hour', p_from) and ts < p_to
  group by site_id, date_trunc('hour', ts)
  on conflict (site_id, hour_ts) do update set
    pv_kwh = excluded.pv_kwh, load_kwh = excluded.load_kwh,
    grid_import_kwh = excluded.grid_import_kwh,
    batt_charge_kwh = excluded.batt_charge_kwh, batt_discharge_kwh = excluded.batt_discharge_kwh,
    soc_min = excluded.soc_min, soc_max = excluded.soc_max, soc_avg = excluded.soc_avg,
    batt_temp_max = excluded.batt_temp_max, grid_on_minutes = excluded.grid_on_minutes,
    samples = excluded.samples;
  get diagnostics n = row_count;
  return n;
end $$;

-- Daily rows are built from hourly rows, using each site's local day (Africa/Lagos by default).
create or replace function public.rollup_daily(p_from date, p_to date)
returns integer language plpgsql security definer set search_path = public as $$
declare n integer;
begin
  insert into public.telemetry_daily as d (
    site_id, day, pv_kwh, load_kwh, grid_import_kwh, batt_charge_kwh, batt_discharge_kwh,
    soc_min, soc_max, batt_temp_max, grid_on_minutes, samples)
  select
    h.site_id,
    (h.hour_ts at time zone s.timezone)::date as day,
    sum(h.pv_kwh), sum(h.load_kwh), sum(h.grid_import_kwh),
    sum(h.batt_charge_kwh), sum(h.batt_discharge_kwh),
    min(h.soc_min), max(h.soc_max), max(h.batt_temp_max),
    sum(h.grid_on_minutes), sum(h.samples)
  from public.telemetry_hourly h
  join public.sites s on s.id = h.site_id
  where (h.hour_ts at time zone s.timezone)::date >= p_from
    and (h.hour_ts at time zone s.timezone)::date <  p_to
  group by h.site_id, (h.hour_ts at time zone s.timezone)::date
  on conflict (site_id, day) do update set
    pv_kwh = excluded.pv_kwh, load_kwh = excluded.load_kwh,
    grid_import_kwh = excluded.grid_import_kwh,
    batt_charge_kwh = excluded.batt_charge_kwh, batt_discharge_kwh = excluded.batt_discharge_kwh,
    soc_min = excluded.soc_min, soc_max = excluded.soc_max,
    batt_temp_max = excluded.batt_temp_max, grid_on_minutes = excluded.grid_on_minutes,
    samples = excluded.samples;
  get diagnostics n = row_count;
  return n;
end $$;

-- Keep raw 5-minute data for p_keep_days (default 30); summaries stay forever.
create or replace function public.purge_old_telemetry(p_keep_days integer default 30)
returns integer language plpgsql security definer set search_path = public as $$
declare n integer;
begin
  delete from public.telemetry where ts < now() - make_interval(days => p_keep_days);
  get diagnostics n = row_count;
  return n;
end $$;

-- Only the backend (service role) may run these.
revoke all on function public.rollup_hourly(timestamptz, timestamptz) from public;
revoke all on function public.rollup_daily(date, date) from public;
revoke all on function public.purge_old_telemetry(integer) from public;
