-- 008_dashboard.sql
-- What the dashboard needs: staff can close findings (with a note), but change nothing else.

alter table public.findings
  add column if not exists resolved_by uuid references public.profiles (id) on delete set null,
  add column if not exists note text;

-- Staff may only change these columns of a finding (the row-level rule in 002 still applies:
-- only staff, only their organisation's sites).
revoke update on public.findings from authenticated;
grant update (status, ts_end, resolved_by, note) on public.findings to authenticated;

-- Staff can read WhatsApp conversations of their organisation's sites (customers cannot).
create policy "staff read conversations" on public.conversations
  for select to authenticated
  using (public.my_role() = 'staff' and site_id is not null and public.can_view_site(site_id));
