from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app import findings
from app.ml import daily
from tests.test_engine import HOME

pytest.importorskip("sklearn")

SITES = [replace(HOME, id=f"id-{i}", code=f"site-{i}") for i in range(3)]
DAY = pd.Timestamp("2026-11-01", tz="Africa/Lagos")


@pytest.fixture
def saved(monkeypatch):
    """Fake the database parts: features per site, and capture the findings."""
    feats = {"site-0": np.zeros(216), "site-1": np.ones(216), "site-2": None}   # site-2 has no data
    monkeypatch.setattr(daily, "day_features", lambda site, day, client=None: feats[site.code])
    out = []
    monkeypatch.setattr(daily, "open_finding", lambda site, **kw: out.append((site.code, kw)) or True)
    return out


def test_uses_modal_and_records_only_unusual_days(saved):
    remote = lambda x: (np.array([0.4, 2.5]), ["soc", "pv2"])     # noqa: E731
    res = daily.run(SITES, day=DAY, remote=remote)
    assert res["model"] == "autoencoder" and res["scored"] == 2 and res["skipped"] == ["site-2"]
    assert res["unusual"] == ["site-1"]
    code, kw = saved[0]
    assert code == "site-1" and kw["kind"] == "unusual_day" and kw["details"]["hint"] == "pv2"
    assert kw["dedupe_key"] == "unusual_day:2026-11-01"


def test_falls_back_to_the_forest_when_modal_is_down(saved):
    def broken(x):
        raise ConnectionError("modal unreachable")

    res = daily.run(SITES, day=DAY, remote=broken, fallback=lambda x: (np.array([3.0, 0.1]), [None, None]))
    assert res["model"] == "isolation_forest" and res["unusual"] == ["site-0"]


class _FakeTable:
    def __init__(self, rows):
        self.rows, self.filters, self.op = rows, {}, "select"

    def select(self, *_):
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def insert(self, row, **_):
        self.op, self.row = "insert", row
        return self

    def execute(self):
        if self.op == "insert":
            self.rows.append({**self.row, "status": "open"})
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=[r for r in self.rows
                                     if all(r.get(k) == v for k, v in self.filters.items())])


class _FakeClient:
    def __init__(self):
        self.rows = []

    def table(self, name):
        return _FakeTable(self.rows)


def test_open_finding_does_not_duplicate():
    client = _FakeClient()
    args = {"kind": "unusual_day", "severity": "info", "dedupe_key": "unusual_day:2026-11-01",
            "ts_start": DAY, "client": client}
    assert findings.open_finding(SITES[0], **args) is True
    assert findings.open_finding(SITES[0], **args) is False
    assert len(client.rows) == 1 and client.rows[0]["ts_start"] == "2026-10-31T23:00:00Z"
