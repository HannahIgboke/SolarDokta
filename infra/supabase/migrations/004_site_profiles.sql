-- 004_site_profiles.sql
-- What kind of place each site is, so the virtual inverter uses the right appliance pattern.

alter table public.sites
  add column load_profile text not null default 'home'
  check (load_profile in ('home', 'home_large', 'clinic', 'school', 'shop'));

update public.sites set load_profile = 'home'       where code = 'lagos-001';
update public.sites set load_profile = 'home_large' where code = 'lagos-002';
update public.sites set load_profile = 'clinic'     where code = 'lagos-003';
update public.sites set load_profile = 'school'     where code = 'ph-001';
