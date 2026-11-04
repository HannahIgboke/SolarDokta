-- 002_security.sql
-- Row Level Security: staff see their organisation's sites; customers see only their own site(s).
-- The backend writes with the service role key, which bypasses these rules.

-- Helper functions (security definer so they can read profiles without recursion).
create or replace function public.my_role()
returns text language sql stable security definer set search_path = public as $$
  select role from public.profiles where id = auth.uid()
$$;

create or replace function public.my_org()
returns uuid language sql stable security definer set search_path = public as $$
  select org_id from public.profiles where id = auth.uid()
$$;

create or replace function public.can_view_site(p_site_id uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.sites s
    where s.id = p_site_id
      and (
        (public.my_role() = 'staff' and s.org_id = public.my_org())
        or s.customer_id = auth.uid()
      )
  )
$$;

-- Turn RLS on everywhere.
alter table public.organisations     enable row level security;
alter table public.profiles          enable row level security;
alter table public.sites             enable row level security;
alter table public.telemetry         enable row level security;
alter table public.telemetry_hourly  enable row level security;
alter table public.telemetry_daily   enable row level security;
alter table public.simulator_state   enable row level security;
alter table public.weather_history   enable row level security;
alter table public.weather_forecast  enable row level security;
alter table public.prices            enable row level security;
alter table public.findings          enable row level security;
alter table public.battery_cycles    enable row level security;
alter table public.alerts            enable row level security;
alter table public.conversations     enable row level security;
alter table public.injected_faults   enable row level security;

-- Organisations: members can read their own organisation.
create policy "read own organisation" on public.organisations
  for select to authenticated using (id = public.my_org());

-- Profiles: everyone reads their own; staff read everyone in their organisation.
create policy "read own profile" on public.profiles
  for select to authenticated using (id = auth.uid());
create policy "staff read org profiles" on public.profiles
  for select to authenticated using (public.my_role() = 'staff' and org_id = public.my_org());

-- Sites.
create policy "read visible sites" on public.sites
  for select to authenticated using (public.can_view_site(id));

-- Everything tied to a site follows the site rule.
create policy "read telemetry"        on public.telemetry        for select to authenticated using (public.can_view_site(site_id));
create policy "read telemetry hourly" on public.telemetry_hourly for select to authenticated using (public.can_view_site(site_id));
create policy "read telemetry daily"  on public.telemetry_daily  for select to authenticated using (public.can_view_site(site_id));
create policy "read findings"         on public.findings         for select to authenticated using (public.can_view_site(site_id));
create policy "read battery cycles"   on public.battery_cycles   for select to authenticated using (public.can_view_site(site_id));
create policy "read alerts"           on public.alerts           for select to authenticated using (public.can_view_site(site_id));

-- Staff can mark findings resolved or dismissed.
create policy "staff update findings" on public.findings
  for update to authenticated
  using (public.my_role() = 'staff' and public.can_view_site(site_id))
  with check (public.my_role() = 'staff' and public.can_view_site(site_id));

-- Shared reference data: any logged-in user can read.
create policy "read weather history"  on public.weather_history  for select to authenticated using (true);
create policy "read weather forecast" on public.weather_forecast for select to authenticated using (true);
create policy "read prices"           on public.prices           for select to authenticated using (true);

-- simulator_state, conversations and injected_faults: backend only (no policies = no client access).
