"""Generate a demo Ed25519 badge key and register its public key with FastAPI."""
import argparse
import base64
import json
import os
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("badge-private-key.json"))
    args = parser.parse_args()
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    args.output.write_text(json.dumps({"private_key": base64.b64encode(raw).decode(), "public_key": base64.b64encode(pub).decode()}), encoding="utf-8")
    try: os.chmod(args.output, 0o600)
    except OSError: pass
    response = httpx.post(f"{args.url}/api/devices", json={"id": args.device, "worker_id": args.worker, "public_key": base64.b64encode(pub).decode()}, headers={"X-API-Key": os.getenv("TRUSTTIER_API_KEY", "")}, timeout=20)
    response.raise_for_status()
    print(f"Registered {args.device}. Keep {args.output} private; never copy it to Supabase or commit it.")


if __name__ == "__main__": main()
