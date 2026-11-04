"""Save and load the virtual inverter's data in Supabase.

Tables used: telemetry (5-minute readings), telemetry_hourly / telemetry_daily (summaries),
simulator_state (where each site's simulation stopped), injected_faults (the answer key).
"""

import math

import pandas as pd

from app.db import get_client, upsert_rows
from app.simulator.engine import TELEMETRY_COLUMNS, SimState
from app.simulator.faults import Fault, _iso
from app.simulator.site import SiteConfig

H = 5 / 60 / 1000          # one 5-minute reading in W -> kWh


def _num(x, nd=2):
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) else round(x, nd)


# ---------- telemetry ----------

def telemetry_rows(site: SiteConfig, out: pd.DataFrame):
    for ts, r in out[TELEMETRY_COLUMNS].iterrows():
        row = {"site_id": site.id, "ts": _iso(ts), "source": "simulator"}
        for c in TELEMETRY_COLUMNS:
            if c == "fault_code":
                row[c] = r[c] or None
            else:
                row[c] = _num(r[c], 4 if c == "batt_soc" else 2)
        yield row


def load_telemetry(site: SiteConfig, start: pd.Timestamp, end: pd.Timestamp, client=None) -> pd.DataFrame:
    """Raw 5-minute readings with start <= ts < end, indexed by local time."""
    client = client or get_client()
    rows, offset = [], 0
    while True:                                     # the API returns at most 1000 rows per call
        page = (client.table("telemetry").select("ts," + ",".join(TELEMETRY_COLUMNS))
                .eq("site_id", site.id).gte("ts", _iso(start)).lt("ts", _iso(end))
                .order("ts").range(offset, offset + 999).execute().data)
        rows += page
        if len(page) < 1000:
            break
        offset += 1000
    if not rows:
        return pd.DataFrame(columns=TELEMETRY_COLUMNS)
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df.pop("ts"), utc=True).dt.tz_convert(site.timezone)
    df.index.name = None
    numeric = [c for c in TELEMETRY_COLUMNS if c != "fault_code"]
    df[numeric] = df[numeric].astype(float)
    return df[TELEMETRY_COLUMNS]


def save_telemetry(site: SiteConfig, out: pd.DataFrame, client=None) -> int:
    return upsert_rows("telemetry", telemetry_rows(site, out), on_conflict="site_id,ts", client=client)


# ---------- summaries (same formulas as the SQL in 003_rollups.sql) ----------

def hourly_summary(out: pd.DataFrame) -> pd.DataFrame:
    df = out.tz_convert("UTC")
    batt_w = df["batt_v"] * df["batt_a"]                 # what the database's batt_w column holds
    g = pd.DataFrame({
        "pv_kwh": (df["pv1_w"] + df["pv2_w"]) * H,
        "load_kwh": df["load_w"] * H,
        "grid_import_kwh": df["grid_w"].clip(lower=0) * H,
        "batt_charge_kwh": batt_w.clip(lower=0) * H,
        "batt_discharge_kwh": (-batt_w).clip(lower=0) * H,
        "soc": df["batt_soc"], "temp": df["batt_temp_c"],
        "grid_on": (df["grid_v"] > 150).astype(int) * 5,
    }).groupby(df.index.floor("1h"))
    h = g[["pv_kwh", "load_kwh", "grid_import_kwh", "batt_charge_kwh", "batt_discharge_kwh"]].sum()
    h["soc_min"], h["soc_max"], h["soc_avg"] = g["soc"].min(), g["soc"].max(), g["soc"].mean()
    h["batt_temp_max"] = g["temp"].max()
    h["grid_on_minutes"] = g["grid_on"].sum()
    h["samples"] = g.size()
    return h


def daily_summary(hourly: pd.DataFrame, tz: str) -> pd.DataFrame:
    local_day = hourly.index.tz_convert(tz).date
    g = hourly.groupby(local_day)
    d = g[["pv_kwh", "load_kwh", "grid_import_kwh", "batt_charge_kwh", "batt_discharge_kwh",
           "grid_on_minutes", "samples"]].sum()
    d["soc_min"], d["soc_max"] = g["soc_min"].min(), g["soc_max"].max()
    d["batt_temp_max"] = g["batt_temp_max"].max()
    return d


def save_summaries(site: SiteConfig, out: pd.DataFrame, client=None) -> tuple[int, int]:
    hourly = hourly_summary(out)
    daily = daily_summary(hourly, site.timezone)
    ints = {"grid_on_minutes", "samples"}

    def rows(df, key, fmt):
        for k, r in df.iterrows():
            row = {"site_id": site.id, key: fmt(k)}
            row.update({c: int(r[c]) if c in ints else _num(r[c], 4) for c in df.columns})
            yield row

    nh = upsert_rows("telemetry_hourly", rows(hourly, "hour_ts", _iso),
                     on_conflict="site_id,hour_ts", client=client)
    nd = upsert_rows("telemetry_daily", rows(daily, "day", lambda d: d.isoformat()),
                     on_conflict="site_id,day", client=client)
    return nh, nd


def refresh_summaries(after: pd.Timestamp, until: pd.Timestamp, tz: str, client=None) -> None:
    """Re-run the database rollups for hours touched by a tick (all sites at once)."""
    client = client or get_client()
    client.rpc("rollup_hourly", {"p_from": _iso(after.floor("1h")),
                                 "p_to": _iso(until + pd.Timedelta(minutes=5))}).execute()
    d0 = after.tz_convert(tz).date()
    d1 = until.tz_convert(tz).date() + pd.Timedelta(days=1)
    client.rpc("rollup_daily", {"p_from": d0.isoformat(), "p_to": d1.isoformat()}).execute()


# ---------- grid conditions (how bad NEPA supply is, by city and date) ----------

def load_grid_conditions(client=None) -> list:
    """Grid conditions from the database; the built-in defaults if the table is missing/empty."""
    from datetime import date

    from app.simulator.grid import DEFAULT_CONDITIONS, GridCondition

    client = client or get_client()
    try:
        rows = client.table("grid_conditions").select("*").order("starts").execute().data
    except Exception:  # noqa: BLE001 - table not created yet (migration 009): use the defaults
        return list(DEFAULT_CONDITIONS)
    if not rows:
        return list(DEFAULT_CONDITIONS)
    return [GridCondition(r["city"], date.fromisoformat(r["starts"]),
                          date.fromisoformat(r["ends"]) if r.get("ends") else None,
                          float(r["hours_per_day"]), float(r["mean_outage_h"]), r.get("note") or "")
            for r in rows]


# ---------- simulator state ----------

def load_state(site: SiteConfig, client=None) -> tuple[SimState | None, pd.Timestamp | None]:
    client = client or get_client()
    rows = client.table("simulator_state").select("*").eq("site_id", site.id).execute().data
    if not rows:
        return None, None
    return SimState.from_dict(rows[0]["state"]), pd.Timestamp(rows[0]["last_ts"]).tz_convert(site.timezone)


def save_state(site: SiteConfig, state: SimState, last_ts: pd.Timestamp, client=None) -> None:
    upsert_rows("simulator_state",
                [{"site_id": site.id, "last_ts": _iso(last_ts), "state": state.to_dict(),
                  "updated_at": _iso(pd.Timestamp.now(tz="UTC"))}],
                on_conflict="site_id", client=client)


# ---------- injected faults ----------

def save_faults(site: SiteConfig, faults: list[Fault], client=None) -> int:
    client = client or get_client()
    if not faults:
        return 0
    client.table("injected_faults").insert([f.to_row(site.id) for f in faults],
                                           returning="minimal").execute()
    return len(faults)


def load_faults(site: SiteConfig, after: pd.Timestamp, until: pd.Timestamp, client=None) -> list[Fault]:
    """Faults that are active at any point between after and until."""
    client = client or get_client()
    rows = (client.table("injected_faults").select("*").eq("site_id", site.id)
            .lte("start_ts", _iso(until))
            .or_(f"end_ts.is.null,end_ts.gt.{_iso(after)}")
            .execute().data)
    return [Fault.from_row(r) for r in rows]


# ---------- long-term health numbers (health_daily, battery_estimates) ----------

def save_health(site: SiteConfig, daily: pd.DataFrame, client=None) -> int:
    """daily: index = local day, columns pr_pv1, pr_pv2, usable_steps, batt_heat_c."""
    rows = [{"site_id": site.id, "day": d.strftime("%Y-%m-%d"),
             "pr_pv1": _num(r.get("pr_pv1"), 4), "pr_pv2": _num(r.get("pr_pv2"), 4),
             "usable_steps": int(r["usable_steps"]) if pd.notna(r.get("usable_steps")) else None,
             "batt_heat_c": _num(r.get("batt_heat_c"), 2)}
            for d, r in daily.iterrows()]
    return upsert_rows("health_daily", rows, on_conflict="site_id,day", client=client)


def load_health(site: SiteConfig, since: pd.Timestamp, client=None) -> pd.DataFrame:
    client = client or get_client()
    rows = (client.table("health_daily").select("day,pr_pv1,pr_pv2,usable_steps,batt_heat_c")
            .eq("site_id", site.id).gte("day", since.strftime("%Y-%m-%d"))
            .order("day").range(0, 9999).execute().data)
    cols = ["pr_pv1", "pr_pv2", "usable_steps", "batt_heat_c"]
    if not rows:
        return pd.DataFrame(columns=cols, dtype=float)
    df = pd.DataFrame(rows)
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop("day"))).tz_localize(site.timezone)
    return df[cols].astype(float)


def save_battery_estimates(site: SiteConfig, est: pd.Series, client=None) -> int:
    rows = [{"site_id": site.id, "ts": _iso(ts), "soh_estimate": _num(v, 4)} for ts, v in est.items()]
    return upsert_rows("battery_estimates", rows, on_conflict="site_id,ts", client=client)


def load_battery_estimates(site: SiteConfig, since: pd.Timestamp, client=None) -> pd.Series:
    client = client or get_client()
    rows = (client.table("battery_estimates").select("ts,soh_estimate").eq("site_id", site.id)
            .gte("ts", _iso(since)).order("ts").range(0, 9999).execute().data)
    if not rows:
        return pd.Series(dtype=float)
    idx = pd.to_datetime([r["ts"] for r in rows], utc=True).tz_convert(site.timezone)
    return pd.Series([float(r["soh_estimate"]) for r in rows], index=idx)


def clear_site(site: SiteConfig, client=None) -> None:
    """Delete a site's simulated data (used before regenerating history)."""
    client = client or get_client()
    for table in ("telemetry", "telemetry_hourly", "telemetry_daily", "simulator_state",
                  "injected_faults", "health_daily", "battery_estimates"):
        client.table(table).delete().eq("site_id", site.id).execute()

