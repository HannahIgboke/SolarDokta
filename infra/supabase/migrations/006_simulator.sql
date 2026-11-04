-- 006_simulator.sql
-- Part D: fault injection and the 5-minute tick.

-- 1. Only allow the fault kinds the simulator knows about, and make lookups by site fast.
alter table public.injected_faults
  add constraint injected_faults_kind_check check (kind in (
    'soiling', 'shading', 'string_failure', 'underrated_panel',
    'battery_fade', 'hot_battery_room', 'overload'));
create index if not exists injected_faults_site_idx on public.injected_faults (site_id, start_ts);

-- 2. Security fix for 003. Supabase lets the anon and authenticated roles run new functions
--    by default, so "revoke ... from public" was not enough: a visitor could have called
--    purge_old_telemetry. Now only the backend (service role) can run these.
revoke execute on function public.rollup_hourly(timestamptz, timestamptz) from anon, authenticated;
revoke execute on function public.rollup_daily(date, date) from anon, authenticated;
revoke execute on function public.purge_old_telemetry(integer) from anon, authenticated;
grant execute on function public.rollup_hourly(timestamptz, timestamptz) to service_role;
grant execute on function public.rollup_daily(date, date) to service_role;
grant execute on function public.purge_old_telemetry(integer) to service_role;
