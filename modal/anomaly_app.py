"""SolarDokta anomaly scorer, running on Modal (serverless: it only exists while it's working).

The backend sends one row of 216 day-features per site; this returns each day's anomaly score,
the threshold, and which health channel looked most unusual. A day costs a few milliseconds of
CPU, far inside Modal's free monthly credit.

Deploy (from the repo root, after `modal setup`):
    modal deploy modal/anomaly_app.py
Quick test from your laptop:
    modal run modal/anomaly_app.py
Redeploy whenever you retrain (ml/models/ is copied into the container at deploy time).
"""

from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "solardokta-anomaly"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", index_url="https://download.pytorch.org/whl/cpu")   # CPU-only: smaller
    .pip_install("numpy", "pandas")
    .add_local_file(ROOT / "backend" / "app" / "__init__.py", "/root/app/__init__.py")
    .add_local_dir(ROOT / "backend" / "app" / "ml", "/root/app/ml", ignore=["**/__pycache__"])
    .add_local_dir(ROOT / "ml" / "models", "/model")
)
app = modal.App(APP_NAME, image=image)


@app.cls(cpu=1.0, memory=1024, scaledown_window=60, timeout=120)
class Scorer:
    @modal.enter()
    def load(self):
        """Runs once when a container starts: load the trained autoencoder."""
        from app.ml.models import AutoencoderDetector

        self.detector = AutoencoderDetector.load(Path("/model"))

    @modal.method()
    def score(self, rows: list[list[float]]) -> dict:
        import numpy as np

        x = np.asarray(rows, dtype=np.float32)
        return {"scores": self.detector.score(x).tolist(),
                "threshold": self.detector.threshold,
                "hints": self.detector.worst_channel(x)}


@app.local_entrypoint()
def smoke_test():
    """`modal run modal/anomaly_app.py`: score one all-zero day to prove the pipeline works."""
    result = Scorer().score.remote([[0.0] * 216])            # 216 = 24 hours x 9 channels
    print(result)
