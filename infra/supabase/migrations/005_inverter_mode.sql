-- 005_inverter_mode.sql
-- The inverter's priority rule for powering the house:
--   SUB = Solar, then Utility (NEPA), then Battery  (battery saved for outages; the BEVE uses this)
--   SBU = Solar, then Battery, then Utility          (uses the battery first to save on NEPA bills)

alter table public.sites
  add column inverter_mode text not null default 'SBU' check (inverter_mode in ('SUB', 'SBU'));

update public.sites set inverter_mode = 'SUB' where code = 'lagos-001';
