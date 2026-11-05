"""Make the key pair for phone notifications (Web Push). Run once:

    python scripts/make_vapid_keys.py

Put VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY in Render's environment (and your local .env).
Keep the private key secret. If you ever change the keys, everyone has to turn alerts on again.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


key = ec.generate_private_key(ec.SECP256R1())
private = key.private_numbers().private_value.to_bytes(32, "big")
public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
print(f"VAPID_PUBLIC_KEY={b64(public)}")
print(f"VAPID_PRIVATE_KEY={b64(private)}")
