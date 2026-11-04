"""A tiny in-memory stand-in for the Supabase client, for tests (no internet, no real database).

Supports the calls our code makes: table().select/eq/gte/lt/lte/order/range/or_ + execute,
and insert / upsert / update / delete.
"""

import itertools
from types import SimpleNamespace

import pandas as pd


def _cmp_value(v):
    if isinstance(v, str) and len(v) >= 10 and v[4] == "-":
        try:
            return pd.Timestamp(v)
        except ValueError:
            return v
    return v


class _Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.op = db, table, [], "select"
        self.payload, self.key, self.order_by, self.lo, self.hi = None, None, None, 0, None

    def select(self, *_):
        return self

    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def gte(self, col, val):
        self.filters.append(lambda r: r.get(col) is not None and _cmp_value(r[col]) >= _cmp_value(val))
        return self

    def lt(self, col, val):
        self.filters.append(lambda r: r.get(col) is not None and _cmp_value(r[col]) < _cmp_value(val))
        return self

    def lte(self, col, val):
        self.filters.append(lambda r: r.get(col) is not None and _cmp_value(r[col]) <= _cmp_value(val))
        return self

    def or_(self, expr):                                  # only "end_ts.is.null,end_ts.gt.<ts>"
        ts = pd.Timestamp(expr.split(".gt.")[1])
        self.filters.append(lambda r: r.get("end_ts") is None or pd.Timestamp(r["end_ts"]) > ts)
        return self

    def order(self, col, desc=False):
        self.order_by = (col, desc)
        return self

    def range(self, lo, hi):
        self.lo, self.hi = lo, hi
        return self

    def insert(self, rows, **_):
        self.op, self.payload = "insert", rows if isinstance(rows, list) else [rows]
        return self

    def upsert(self, rows, on_conflict, **_):
        self.op, self.payload, self.key = "upsert", rows, on_conflict.split(",")
        return self

    def update(self, values):
        self.op, self.payload = "update", values
        return self

    def delete(self):
        self.op = "delete"
        return self

    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        match = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "select":
            if self.order_by:
                col, desc = self.order_by
                match = sorted(match, key=lambda r: _cmp_value(r[col]), reverse=desc)
            hi = None if self.hi is None else self.hi + 1
            return SimpleNamespace(data=[dict(r) for r in match[self.lo:hi]])
        if self.op == "insert":
            out = []
            for r in self.payload:
                r = {"id": str(next(self.db.ids)), "status": "open", **r}
                rows.append(r)
                out.append(dict(r))
            return SimpleNamespace(data=out)
        if self.op == "upsert":
            for r in self.payload:
                same = [x for x in rows if all(x.get(k) == r[k] for k in self.key)]
                if same:
                    same[0].update(r)
                else:
                    rows.append(dict(r))
            return SimpleNamespace(data=[])
        if self.op == "update":
            for r in match:
                r.update(self.payload)
            return SimpleNamespace(data=match)
        if self.op == "delete":
            self.db.tables[self.table] = [r for r in rows if r not in match]
            return SimpleNamespace(data=match)
        raise ValueError(self.op)


class _Bucket:
    def __init__(self, files):
        self.files = files

    def upload(self, path, data, options=None):
        self.files[path] = data

    def create_signed_url(self, path, expires_in):
        return {"signedURL": f"https://files.test/{path}?token=x"}


class _Storage:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    def from_(self, bucket):
        return _Bucket(self.files)


class FakeDB:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.ids = itertools.count(1)
        self.storage = _Storage()

    def table(self, name):
        return _Query(self, name)

    def rpc(self, *_args, **_kw):
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=None))
