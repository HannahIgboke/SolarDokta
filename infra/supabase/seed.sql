-- seed.sql
-- One demo installer organisation and six simulated sites across Nigeria.
-- Prices are placeholders: replace them with current figures before using the money view.

insert into public.organisations (id, name)
values ('00000000-0000-0000-0000-000000000001', 'Demo Solar Installers Ltd');

insert into public.sites
  (code, org_id, name, city, latitude, longitude, pv1_kwp, pv2_kwp, tilt_deg, azimuth_deg,
   inverter_kw, battery_kwh, battery_chemistry, tariff_band, generator_fuel)
values
  -- Two unequal panel groups (strings), like many real installs.
  ('lagos-001', '00000000-0000-0000-0000-000000000001', 'Ikeja home', 'Lagos',
   6.60180, 3.35150, 3.60, 1.40, 10, 180, 6.0, 10.0, 'lifepo4', 'A', 'petrol'),
  ('lagos-002', '00000000-0000-0000-0000-000000000001', 'Lekki duplex', 'Lagos',
   6.44740, 3.47250, 4.00, 4.00, 10, 180, 10.0, 15.0, 'lifepo4', 'A', 'diesel'),
  ('lagos-003', '00000000-0000-0000-0000-000000000001', 'Surulere clinic', 'Lagos',
   6.49980, 3.35440, 3.00, 3.00, 12, 180, 8.0, 20.0, 'lifepo4', 'B', 'diesel'),
  ('abuja-001', '00000000-0000-0000-0000-000000000001', 'Gwarinpa home', 'Abuja',
   9.10870, 7.40440, 2.50, 2.50, 12, 180, 5.0, 7.5, 'lifepo4', 'B', 'petrol'),
  ('kano-001', '00000000-0000-0000-0000-000000000001', 'Nassarawa shop', 'Kano',
   12.00220, 8.59200, 2.00, 0.00, 15, 180, 3.5, 4.8, 'lead_acid', 'C', 'petrol'),
  ('ph-001', '00000000-0000-0000-0000-000000000001', 'GRA school', 'Port Harcourt',
   4.81560, 7.04980, 3.50, 3.50, 8, 180, 8.0, 15.0, 'lifepo4', 'A', 'diesel');

insert into public.prices (item, unit, price_ngn, effective_from, source) values
  ('petrol',      'ngn_per_litre', 1000.00, '2026-10-01', 'PLACEHOLDER - update'),
  ('diesel',      'ngn_per_litre', 1300.00, '2026-10-01', 'PLACEHOLDER - update'),
  ('grid_band_a', 'ngn_per_kwh',    210.00, '2026-10-01', 'PLACEHOLDER - update'),
  ('grid_band_b', 'ngn_per_kwh',     65.00, '2026-10-01', 'PLACEHOLDER - update'),
  ('grid_band_c', 'ngn_per_kwh',     50.00, '2026-10-01', 'PLACEHOLDER - update'),
  ('grid_band_d', 'ngn_per_kwh',     40.00, '2026-10-01', 'PLACEHOLDER - update'),
  ('grid_band_e', 'ngn_per_kwh',     35.00, '2026-10-01', 'PLACEHOLDER - update');
