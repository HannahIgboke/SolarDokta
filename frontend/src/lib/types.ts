// Shapes of the data the backend sends to the dashboard.

export type PanelString = {
  id: string;
  number: number;
  kwp: number;
  panels: number;
  now_w: number;
  could_make_w: number | null;
  status: "ok" | "dead" | "weak" | "shaded" | "dusty";
};

export type Appliance = { name: string; watts: number; on: boolean };

export type Live = {
  error?: string;
  reading_time: string;
  stale: boolean;
  is_day: boolean;
  sun: number;
  solar_w: number;
  held_back_w: number;
  house_w: number;
  nepa_on: boolean;
  nepa_w: number;
  strings: PanelString[];
  battery: {
    percent: number;
    power_w: number;
    energy_left_kwh: number;
    full_kwh: number;
    size_kwh: number;
    temp_c: number | null;
    hot: boolean;
    fading: boolean;
    status: "charging" | "discharging" | "resting";
    tonight?: string;
  };
  inverter: { kw: number; mode: "SUB" | "SBU"; load_percent: number; fault: string | null };
  appliances: Appliance[];
  appliances_source?: "yours" | "usual";
  problems: string[];
  headline: string;
  device?: Device;
};

export type Device = {
  name: string;
  connected: boolean;
  last_seen_minutes: number;
  connection: string;
  readings_today: number | null;
  readings_expected_today: number;
  simulated: boolean;
};

export type Usage = {
  error?: string;
  mode: "hours" | "days";
  span: string;
  message?: string;
  points: { label: string; solar_kwh: number | null; use_kwh: number | null; nepa_kwh: number | null;
            battery_low: number | null; battery_high: number | null; battery_temp: number | null;
            light_hours: number | null }[];
  totals?: { solar_kwh: number; use_kwh: number; nepa_kwh: number; light_hours: number;
             from_solar_percent: number | null; saved_ngn: number; days: number };
  story?: string[];
  estimate?: boolean;
};

export type TodayPoint = {
  time: string;
  solar_w?: number;
  could_make_w?: number;
  house_w?: number;
  battery_percent?: number;
  nepa_on?: boolean;
};
export type Today = { date?: string; points: TodayPoint[]; solar_kwh?: number; house_kwh?: number };

export type TomorrowPlan = {
  error?: string;
  date: string;
  sky: "sunny" | "partly cloudy" | "cloudy";
  expected_solar_kwh: number;
  expected_nepa_hours?: number;
  daytime_cloud_percent?: number;
  weak_panel_strings?: Record<string, number>;
  normal_daily_use_kwh?: number;
  solar_covers_percent?: number | null;
  best_hours_for_heavy_appliances?: string[] | null;
  hourly_solar_kw?: number[];
  hourly_use_kw?: number[];
};

export type BatteryNow = {
  error?: string;
  tonight?: string;
  normal_night_use_kwh?: number;
  full_battery_holds_kwh?: number;
  needed_until_morning_kwh?: number;
  energy_left_kwh?: number;
};

export type Problem = {
  problem: string;
  what_to_do: string;
  urgency: "critical" | "warning" | "info";
  since: string;
  panel_string?: string;
};
export type Problems = { open_problems: Problem[]; all_clear: boolean; [k: string]: unknown };

export type MoneyView = {
  error?: string;
  period_days: number;
  saved_by_solar_ngn: number;
  saved_per_month_ngn: number;
  nepa_cost_ngn: number;
  nepa_bought_kwh: number;
  nepa_available_percent: number;
  generator_fuel_avoided_litres?: number;
  fuel_price?: string;
  tariff: string;
  warning?: string;
};
export type MoneyHistory = {
  months: { month: string; days: number; saved_ngn: number; nepa_spend_ngn: number; solar_kwh: number }[];
  estimate?: boolean;
};

export type BatteryCard = {
  chemistry: string;
  nameplate_kwh: number;
  health_percent?: number;
  usable_kwh_now?: number;
  status?: string;
  health?: string;
  health_lost_per_year_percent?: number;
  years_until_80_percent?: number;
  equivalent_full_cycles?: number;
  days_above_35C_percent?: number;
  trend_confidence?: string;
  warning?: string;
  deep_discharges_measured: number;
};

export type CanIRun = {
  verdict: "yes" | "yes_but" | "no" | "need_watts" | "no_data";
  appliance?: string;
  reasons?: string[];
  tips?: string[];
  battery_percent_after?: number;
  powered_by?: string;
  message?: string;
};

export type LightTracker = {
  error?: string;
  days: { day: string; hours: number }[];
  average_hours_per_day: number;
  worst_day: { day: string; hours: number };
  normal_hours_for_band: number;
  tariff_band: string;
  home_blackout_hours: number;
  home_blackouts: number;
  battery_lowest_percent_avg: number | null;
  situation?: string;
  situation_since?: string;
};

export type HeatOutlook = {
  el_nino: string;
  battery_average_c?: number;
  battery_hottest_c?: number;
  battery_hot_days_last_30?: number;
  ageing_speed_vs_25c?: number;
  extra_wear_percent_per_year?: number;
  extra_wear_this_el_nino_season_percent?: number;
  tomorrow_high_c?: number;
  heatwave_tomorrow?: boolean;
  panel_midday_loss_percent?: number;
  normal_wear_percent_per_year?: number;
  life_lost_months_this_season?: number;
  daily_max_c?: { day: string; c: number }[];
  tips: string[];
};

export type BatteryReport = {
  chemistry: string; nameplate_kwh: number; install_date: string | null; age_years?: number;
  soh_percent: number | null; soc_percent: number | null; usable_kwh: number;
  cycles: number; rated_cycles: number; cycles_per_year: number;
  typical_depth_of_discharge_percent: number | null;
  battery_avg_temp_c_30d: number | null; hot_days_percent_30d: number | null; ageing_speed_now: number;
  fade_per_year_percent: number; fade_measured: boolean; fade_el_nino_percent: number; fade_cool_percent: number;
  reaches_80_at: string | null; reaches_80_years: number | null; reaches_80_if_cool_at: string | null;
  life_lost_to_heat_months: number | null; el_nino_extra_months: number; replace_around: string | null;
  grade: "A" | "B" | "C" | "D"; grade_text: string;
  history: { ts: string; soh: number; install?: boolean }[];
  projection: { ts: string; soh: number }[]; projection_cool: { ts: string; soh: number }[];
  measured: boolean; summary: string[];
};

export type Upload = {
  id: string;
  kind: "token_receipt" | "fuel_receipt" | "voice_note" | "photo";
  component: string | null;
  status: "pending" | "read" | "failed";
  extracted: Record<string, unknown>;
  error?: string | null;
  created_at: string;
  url?: string | null;
};

export type ApplianceRow = { name: string; watts: number; qty: number };

export type FleetSite = {
  code: string;
  name: string;
  city: string;
  latitude: number;
  longitude: number;
  simulated: boolean;
  open: { critical: number; warning: number; info: number };
  worst: "critical" | "warning" | "info" | null;
  problems: string[];
  battery_health: number | null;
  battery?: number;
  solar_w?: number;
  house_w?: number;
  nepa_on?: boolean;
  minutes_since_reading: number | null;
  online: boolean;
  fault_code?: string | null;
  heat: { battery_avg_c: number | null; hot_days: number; ageing_speed: number | null; risk: "low" | "medium" | "high" };
  light_hours_7d: number | null;
  blackouts_7d: { count: number; hours: number };
};
export type Fleet = {
  totals: { sites: number; online: number; critical: number; warning: number; solar_now_kw: number;
            need_visit: number; blackout_hours_7d: number; heat_risk_sites: number; light_hours_avg: number };
  sites: FleetSite[];
};

export type Finding = {
  id: string;
  site: string;
  site_name: string;
  kind: string;
  severity: "critical" | "warning" | "info";
  status: "open" | "resolved" | "dismissed";
  problem: string;
  what_to_do: string;
  ts_start: string;
  ts_end: string | null;
  details: Record<string, unknown>;
  score: number | null;
  note: string | null;
};

export type History = {
  strings: { day: string; pv1: number | null; pv2: number | null; battery_heat_c: number | null }[];
  battery: { ts: string; day: string; soh: number }[];
  battery_trend: { from: { ts: string; soh: number }; to: { ts: string; soh: number }; fade_per_year: number } | null;
  energy: { day: string; solar_kwh: number | null; use_kwh: number | null; nepa_kwh: number | null;
            light_hours: number | null; battery_low: number | null; battery_temp_max: number | null }[];
};

export type WhatIfRun = {
  blackout_hours: number;
  nights_without_power: number;
  battery_lowest_percent: number;
  solar_kwh: number;
  nepa_hours_per_day: number;
  battery_hottest_c: number;
  battery_ageing_speed: number;
  battery_wear_percent: number;
  days: { day: string; battery_low: number; blackout_hours: number; solar_kwh: number; nepa_hours: number }[];
};
export type WhatIf = { from: string; days: number; as_is: WhatIfRun; what_if: WhatIfRun; summary: string[] };
