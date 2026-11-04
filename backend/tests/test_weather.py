import pandas as pd

from app.weather import nasa_power, open_meteo
from app.weather.points import weather_point


def test_weather_point_groups_nearby_sites():
    ikeja = weather_point(6.6018, 3.3515)
    lekki = weather_point(6.4474, 3.4725)
    kano = weather_point(12.0022, 8.592)
    assert ikeja == lekki == weather_point(6.5, 3.5)
    assert kano == weather_point(12.0, 8.5)


def test_nasa_power_parse_handles_fill_and_utc():
    payload = {
        "header": {"fill_value": -999.0},
        "parameters": {"ALLSKY_SFC_SW_DWN": {"units": "Wh/m^2"}, "T2M": {"units": "C"}},
        "properties": {"parameter": {
            "ALLSKY_SFC_SW_DWN": {"2024010111": 650.5, "2024010112": -999.0, "2024010100": -0.2},
            "T2M": {"2024010111": 31.2, "2024010112": 32.0, "2024010100": 24.1},
        }},
    }
    df = nasa_power.parse_response(payload)
    assert list(df.columns) == ["ghi_wm2", "temp_c"]
    assert str(df.index.tz) == "UTC"
    assert df.index[0] == pd.Timestamp("2024-01-01 00:00", tz="UTC")   # sorted
    assert df.loc[pd.Timestamp("2024-01-01 11:00", tz="UTC"), "ghi_wm2"] == 650.5
    assert pd.isna(df.loc[pd.Timestamp("2024-01-01 12:00", tz="UTC"), "ghi_wm2"])  # fill -> NaN
    assert df.loc[pd.Timestamp("2024-01-01 00:00", tz="UTC"), "ghi_wm2"] == 0      # clipped


def test_open_meteo_parse():
    payload = {"hourly": {
        "time": ["2026-10-30T00:00", "2026-10-30T01:00"],
        "shortwave_radiation": [0.0, 0.0],
        "temperature_2m": [25.1, 24.8],
        "cloud_cover": [80, 75],
    }}
    df = open_meteo.parse_response(payload)
    assert list(df.columns) == ["ghi_wm2", "temp_c", "cloud_cover_pct"]
    assert df.index[1] == pd.Timestamp("2026-10-30 01:00", tz="UTC")
    assert df["cloud_cover_pct"].iloc[0] == 80.0
