"""Anomaly models: a PyTorch autoencoder, and an Isolation Forest as the simpler fallback.

Both learn what NORMAL days look like (trained on clean days only) and give every new day an
anomaly score. A day is flagged when its score is above a threshold set on held-out clean days
(by default only 1 clean day in 200 would be flagged by chance).

The autoencoder squeezes the 216 numbers of a day through a 16-number bottleneck and tries to
rebuild the HEALTH channels (solar strings, battery). Normal days rebuild well; unusual days
rebuild badly. Which channel rebuilt worst also hints at WHAT is unusual (e.g. "pv2").

The "context" channels (weather, house usage, NEPA) are random from day to day and are not a
fault in themselves, so they are handed straight to the decoder instead of being rebuilt.
Otherwise the model would mostly flag days with unusual NEPA cuts, which is not our job here.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from app.ml.features import CHANNELS, FEATURES, HOURS

THRESHOLD_QUANTILE = 0.995
CONTEXT = ["pv_expected", "load", "grid_on", "grid_power"]
TARGETS = [c for c in CHANNELS if c not in CONTEXT]
CTX_IDX = [i for i, f in enumerate(FEATURES) if f.rsplit("_", 1)[0] in CONTEXT]
TGT_IDX = [i for i, f in enumerate(FEATURES) if f.rsplit("_", 1)[0] in TARGETS]
MIN_STD = 0.02              # night-time solar is always 0; don't divide by ~0


@dataclass
class Scaler:
    mean: np.ndarray
    std: np.ndarray

    @staticmethod
    def fit(x: np.ndarray) -> "Scaler":
        return Scaler(x.mean(axis=0), np.maximum(x.std(axis=0), MIN_STD))

    def __call__(self, x: np.ndarray) -> np.ndarray:
        return ((x - self.mean) / self.std).astype(np.float32)


def _split_validation(n: int, frac: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    idx = np.random.default_rng(seed).permutation(n)
    k = max(1, int(n * frac))
    return idx[k:], idx[:k]


# ---------- autoencoder ----------

def _build(bottleneck: int):
    import torch
    from torch import nn

    class ContextAutoencoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Linear(len(FEATURES), 128), nn.ReLU(), nn.Dropout(0.1),
                nn.Linear(128, bottleneck), nn.ReLU())
            self.decoder = nn.Sequential(
                nn.Linear(bottleneck + len(CTX_IDX), 128), nn.ReLU(),
                nn.Linear(128, len(TGT_IDX)))

        def forward(self, x):
            z = self.encoder(x)
            return self.decoder(torch.cat([z, x[:, CTX_IDX]], dim=1))

    return ContextAutoencoder()


@dataclass
class AutoencoderDetector:
    scaler: Scaler
    threshold: float
    state: dict = field(repr=False)
    bottleneck: int = 16

    @staticmethod
    def fit(x_clean: np.ndarray, epochs: int = 150, bottleneck: int = 16, seed: int = 0,
            verbose: bool = False) -> "AutoencoderDetector":
        import torch

        torch.manual_seed(seed)
        tr, va = _split_validation(len(x_clean), 0.15, seed)
        scaler = Scaler.fit(x_clean[tr])
        xt = torch.tensor(scaler(x_clean[tr]))
        xv = torch.tensor(scaler(x_clean[va]))
        net = _build(bottleneck)
        opt = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-5)
        loss_fn = torch.nn.MSELoss()
        for epoch in range(epochs):
            net.train()
            for batch in torch.randperm(len(xt)).split(64):
                opt.zero_grad()
                loss = loss_fn(net(xt[batch]), xt[batch][:, TGT_IDX])
                loss.backward()
                opt.step()
            if verbose and (epoch + 1) % 50 == 0:
                net.eval()
                with torch.no_grad():
                    print(f"    epoch {epoch + 1}: train {loss.item():.3f}  "
                          f"validation {loss_fn(net(xv), xv[:, TGT_IDX]).item():.3f}")
        det = AutoencoderDetector(scaler, 0.0, net.state_dict(), bottleneck)
        det.threshold = float(np.quantile(det.score(x_clean[va]), THRESHOLD_QUANTILE))
        return det

    def _errors(self, x: np.ndarray) -> np.ndarray:
        """Squared reconstruction error per health feature (days x 120)."""
        import torch

        net = _build(self.bottleneck)
        net.load_state_dict(self.state)
        net.eval()
        z = torch.tensor(self.scaler(x))
        with torch.no_grad():
            return ((net(z) - z[:, TGT_IDX]) ** 2).numpy()

    def score(self, x: np.ndarray) -> np.ndarray:
        return self._errors(x).mean(axis=1)

    def worst_channel(self, x: np.ndarray) -> list[str]:
        """For each day, the channel that rebuilt worst (a hint at what is wrong)."""
        per_channel = self._errors(x).reshape(len(x), len(TARGETS), HOURS).mean(axis=2)
        return [TARGETS[i] for i in per_channel.argmax(axis=1)]

    def save(self, folder: Path) -> None:
        import torch

        folder.mkdir(parents=True, exist_ok=True)
        torch.save(self.state, folder / "autoencoder.pt")
        (folder / "autoencoder.json").write_text(json.dumps({
            "threshold": self.threshold, "bottleneck": self.bottleneck, "features": FEATURES,
            "mean": self.scaler.mean.tolist(), "std": self.scaler.std.tolist()}, indent=1))

    @staticmethod
    def load(folder: Path) -> "AutoencoderDetector":
        import torch

        meta = json.loads((folder / "autoencoder.json").read_text())
        if meta["features"] != FEATURES:
            raise ValueError("Saved model was trained on different features; retrain it")
        scaler = Scaler(np.array(meta["mean"], dtype=np.float32), np.array(meta["std"], dtype=np.float32))
        state = torch.load(folder / "autoencoder.pt", weights_only=True)
        return AutoencoderDetector(scaler, meta["threshold"], state, meta["bottleneck"])


# ---------- isolation forest (fallback, no PyTorch needed) ----------

@dataclass
class ForestDetector:
    scaler: Scaler
    threshold: float
    model: object = field(repr=False)

    @staticmethod
    def fit(x_clean: np.ndarray, seed: int = 0) -> "ForestDetector":
        from sklearn.ensemble import IsolationForest

        tr, va = _split_validation(len(x_clean), 0.15, seed)
        scaler = Scaler.fit(x_clean[tr])
        model = IsolationForest(n_estimators=300, random_state=seed).fit(scaler(x_clean[tr]))
        det = ForestDetector(scaler, 0.0, model)
        det.threshold = float(np.quantile(det.score(x_clean[va]), THRESHOLD_QUANTILE))
        return det

    def score(self, x: np.ndarray) -> np.ndarray:
        return -self.model.score_samples(self.scaler(x))      # higher = more unusual

    def save(self, folder: Path) -> None:
        import joblib

        folder.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, folder / "forest.joblib")

    @staticmethod
    def load(folder: Path) -> "ForestDetector":
        import joblib

        return joblib.load(folder / "forest.joblib")


# ---------- daily scores -> alarms ----------

def to_alarms(days: pd.DatetimeIndex, scores: np.ndarray, threshold: float,
              hints: list[str] | None = None, kind: str = "anomaly",
              start_after: int = 1, end_after: int = 2) -> list:
    """Days above the threshold become alarms ("something is unusual"), raised at day end."""
    from app.detect.rules import FAULT, OK, Alarm, episodes

    ev = pd.Series(np.where(scores > threshold, FAULT, OK), index=days)
    hint = pd.Series(hints if hints is not None else [None] * len(days), index=days)
    alarms = []
    for s, r, e in episodes(ev, start_after, end_after):
        bad = ev.loc[s:r].index
        top = hint.loc[bad].mode()
        alarms.append(Alarm(kind, s, r + pd.Timedelta(days=1), e,
                            details={"score": round(float(scores[days.get_loc(r)] / threshold), 2),
                                     "hint": top.iloc[0] if len(top) else None}))
    return alarms
