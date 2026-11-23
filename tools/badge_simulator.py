"""Create signed, chained demo badge events and submit them to a TrustTier API."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def make_event(key: Ed25519PrivateKey, device_id: str, worker_id: str, job_id: str | None,
               event_type: str, tier: str, previous_hash: str, *, tamper: bool = False) -> dict:
    body = {
        "id": str(uuid.uuid4()), "device_id": device_id, "worker_id": worker_id,
        "job_id": job_id, "client_id": "CLT-0350", "type": event_type,
        "evidence_tier": tier, "device_ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": {"client_confirmation": True, "demo": True}, "prev_hash": previous_hash,
    }
    digest = hashlib.sha256(previous_hash.encode() + canonical(body)).hexdigest()
    signature = key.sign(digest.encode())
    if tamper:
        body["payload"]["client_confirmation"] = False
    return {**body, "hash": digest, "signature": base64.b64encode(signature).decode()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--device", default="DEMO-ESP32-001")
    parser.add_argument("--worker", default="RDR-025")
    parser.add_argument("--job", default="demo-job-001")
    parser.add_argument("--offline", action="store_true", help="Buffer a 3-event batch before submitting")
    parser.add_argument("--tampered", action="store_true", help="Include an altered payload with stale signature")
    parser.add_argument("--key-file", type=Path, default=Path(".badge-demo-key.json"))
    args = parser.parse_args()

    if args.key_file.exists():
        key_data = json.loads(args.key_file.read_text(encoding="utf-8"))
        private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(key_data["private_key"]))
    else:
        private_key = Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        public_bytes = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        args.key_file.write_text(json.dumps({"private_key": base64.b64encode(private_bytes).decode(), "public_key": base64.b64encode(public_bytes).decode()}), encoding="utf-8")
        try:
            os.chmod(args.key_file, 0o600)
        except OSError:
            pass
    public_key = base64.b64encode(private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    headers = {"X-API-Key": os.getenv("TRUSTTIER_API_KEY", "")}

    with httpx.Client(timeout=30) as client:
        registered = client.post(f"{args.url}/api/devices", json={"id": args.device, "worker_id": args.worker, "public_key": public_key}, headers=headers)
        registered.raise_for_status()
        events, prev = [], ""
        sequence = [("arrive", "nfc"), ("start", "signed"), ("finish", "signed")]
        for index, (event_type, tier) in enumerate(sequence):
            tamper = args.tampered and index == len(sequence) - 1
            event = make_event(private_key, args.device, args.worker, args.job, event_type, tier, prev, tamper=tamper)
            events.append(event)
            prev = event["hash"]
        if args.offline:
            time.sleep(1)
        result = client.post(f"{args.url}/api/sync", json={"events": events}, headers=headers)
        result.raise_for_status()
        print(json.dumps(result.json(), indent=2))


if __name__ == "__main__":
    main()
