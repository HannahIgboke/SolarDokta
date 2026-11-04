"""What each panel string SHOULD produce, from the weather and the site's setup (physics).

Same pvlib chain as the simulator, but without the random cloud flicker: detectors only know
hourly weather (satellite / forecast data), never the true 5-minute sunlight.
"""

import pandas as pd

from app.simulator.pv import pv_power, spread_hourly_ghi
from app.simulator.site import SiteConfig


def expected_power(site: SiteConfig, hourly: pd.DataFrame, label: str,
                   index: pd.DatetimeIndex) -> pd.DataFrame:
    """Expected pv1/pv2 power (W) and outdoor temperature for each 5-minute step in `index`."""
    start = index[0].tz_convert("UTC").floor("1D")
    end = index[-1].tz_convert("UTC").ceil("1D") + pd.Timedelta(days=1)
    w5 = spread_hourly_ghi(hourly, site, start, end, label=label, flicker=False)
    pv = pv_power(w5, site).tz_convert(index.tz)
    out = pd.DataFrame({"pv1_exp_w": pv["pv1_w"], "pv2_exp_w": pv["pv2_w"],
                        "outdoor_temp_c": w5["temp_c"].tz_convert(index.tz)})
    return out.reindex(index)
