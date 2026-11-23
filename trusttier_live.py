"""Live ingestion and demo persistence for signed TrustTier badge events."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api")
_lock = threading.RLock()
_events: dict[str, dict[str, Any]] = {}
_devices: dict[str, dict[str, Any]] = {}
_scores: dict[str, dict[str, Any]] = {}
_history: list[dict[str, Any]] = []
_disputes: list[dict[str, Any]] = []
_reviews: list[dict[str, Any]] = []
_jobs: dict[str, dict[str, Any]] = {}

PRIOR = float(os.getenv("TRUSTTIER_PRIOR", "0.6209"))
LIKELIHOOD = {
    "self": float(os.getenv("TRUSTTIER_LR_SELF", "0.09")),
    "nfc": float(os.getenv("TRUSTTIER_LR_NFC", "1.8858")),
    "signed": float(os.getenv("TRUSTTIER_LR_SIGNED", "48.95")),
}


class BadgeEvent(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    device_id: str = Field(min_length=1, max_length=100)
    worker_id: str = Field(min_length=1, max_length=100)
    job_id: str | None = None
    client_id: str | None = None
    type: str
    evidence_tier: str
    device_ts: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    signature: str
    prev_hash: str = ""
    hash: str

    def validate_domain(self) -> None:
        if self.type not in {"arrive", "start", "finish"}:
            raise ValueError("unsupported event type")
        if self.evidence_tier not in LIKELIHOOD:
            raise ValueError("unsupported evidence tier")


class SyncBatch(BaseModel):
    events: list[BadgeEvent] = Field(min_length=1, max_length=500)


class DeviceRegistration(BaseModel):
    id: str
    worker_id: str
    public_key: str
    algorithm: str = "ed25519"


class JobCreate(BaseModel):
    id: str | None = None
    worker_id: str
    client_id: str
    title: str = Field(min_length=1, max_length=200)
    address: str = Field(default="", max_length=500)


class ReviewCreate(BaseModel):
    job_id: str
    worker_id: str
    client_id: str
    stars: int = Field(ge=1, le=5)
    body: str = Field(default="", max_length=2000)


class DisputeCreate(BaseModel):
    job_id: str
    worker_id: str
    client_id: str
    reason: str = Field(min_length=1, max_length=2000)


def event_body(event: BadgeEvent) -> dict[str, Any]:
    value = event.model_dump(mode="json", exclude={"signature", "hash"})
    return value


def expected_hash(event: BadgeEvent) -> str:
    body = json.dumps(event_body(event), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(event.prev_hash.encode() + body).hexdigest()


def verify_signature(event: BadgeEvent, device: dict[str, Any]) -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = base64.b64decode(device["public_key"], validate=True)
        signature = base64.b64decode(event.signature, validate=True)
        Ed25519PublicKey.from_public_bytes(key).verify(signature, event.hash.encode())
        return True
    except Exception:
        return False


def _client():
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def _save(table: str, row: dict[str, Any]) -> None:
    client = _client()
    if client:
        client.table(table).upsert(row).execute()


def _insert(table: str, row: dict[str, Any]) -> None:
    client = _client()
    if client:
        client.table(table).insert(row).execute()


def _read(table: str, order: str | None = None) -> list[dict[str, Any]]:
    client = _client()
    if client:
        query = client.table(table).select("*")
        if order:
            query = query.order(order, desc=True)
        return query.limit(500).execute().data or []
    return []


def register_device(reg: DeviceRegistration) -> None:
    if reg.algorithm != "ed25519":
        raise HTTPException(422, "Only Ed25519 devices are currently supported")
    try:
        raw = base64.b64decode(reg.public_key, validate=True)
        if len(raw) != 32:
            raise ValueError
    except Exception as exc:
        raise HTTPException(422, "public_key must be a base64 Ed25519 public key") from exc
    record = reg.model_dump()
    _devices[reg.id] = record
    _save("devices", record)


def _apply_score(worker_id: str, event: dict[str, Any]) -> tuple[float, float]:
    old = _scores.get(worker_id, {"worker_id": worker_id, "score": PRIOR, "evidence_counts": {"self": 0, "nfc": 0, "signed": 0}})
    previous = float(old["score"])
    prior_odds = PRIOR / (1 - PRIOR)
    posterior_odds = prior_odds * LIKELIHOOD[event["evidence_tier"]]
    score = posterior_odds / (1 + posterior_odds)
    counts = dict(old.get("evidence_counts", {}))
    counts[event["evidence_tier"]] = int(counts.get(event["evidence_tier"], 0)) + 1
    updated = {"worker_id": worker_id, "score": score, "evidence_counts": counts, "updated_at": datetime.now(timezone.utc).isoformat()}
    _scores[worker_id] = updated
    history = {"worker_id": worker_id, "event_id": event["id"], "previous_score": previous, "score": score, "evidence_tier": event["evidence_tier"]}
    _history.append(history)
    _save("trust_scores", updated)
    _insert("trust_score_history", history)
    return previous, score


def sync_events(batch: SyncBatch) -> dict[str, Any]:
    results = []
    with _lock:
        for model in batch.events:
            event = model.model_dump(mode="json")
            reason = None
            device = _devices.get(model.device_id)
            if not device:
                # Allow DB-registered devices in remote mode.
                rows = [d for d in _read("devices") if d.get("id") == model.device_id]
                device = rows[0] if rows else None
            if model.id in _events or any(e.get("id") == model.id for e in _read("events")):
                reason = "duplicate event id"
            elif not device:
                reason = "unknown device"
            else:
                try:
                    model.validate_domain()
                except ValueError as exc:
                    reason = str(exc)
                last_hash = device.get("last_hash", "")
                if reason is None and model.prev_hash != last_hash:
                    reason = "hash chain prev_hash mismatch"
                if reason is None and expected_hash(model) != model.hash:
                    reason = "event hash mismatch"
                if reason is None and not verify_signature(model, device):
                    reason = "invalid device signature"
            event.update(verified=reason is None, rejection_reason=reason, synced_at=datetime.now(timezone.utc).isoformat())
            _events[model.id] = event
            try:
                _insert("events", event)
            except Exception as exc:
                event["verified"] = False
                event["rejection_reason"] = f"database write failed: {type(exc).__name__}"
                reason = event["rejection_reason"]
            score_change = None
            if reason is None:
                device["last_hash"] = model.hash
                device["last_seen_at"] = event["synced_at"]
                _devices[model.device_id] = device
                _save("devices", device)
                before, after = _apply_score(model.worker_id, event)
                score_change = {"before": before, "after": after}
            results.append({"id": model.id, "verified": reason is None, "reason": reason, "score_change": score_change})
    return {"accepted": sum(r["verified"] for r in results), "rejected": sum(not r["verified"] for r in results), "results": results}


@router.post("/sync")
def api_sync(batch: SyncBatch, x_api_key: str | None = Header(default=None)):
    expected = os.getenv("TRUSTTIER_API_KEY", "")
    if expected and x_api_key != expected:
        raise HTTPException(401, "invalid API key")
    return sync_events(batch)


@router.post("/devices")
def api_register_device(registration: DeviceRegistration, x_api_key: str | None = Header(default=None)):
    expected = os.getenv("TRUSTTIER_API_KEY", "")
    if expected and x_api_key != expected:
        raise HTTPException(401, "invalid API key")
    register_device(registration)
    return {"registered": registration.id}


@router.get("/live/events")
def live_events():
    return sorted(_events.values(), key=lambda e: e.get("synced_at", ""), reverse=True)[:100] or _read("events", "synced_at")


@router.get("/workers")
def workers():
    rows = _read("trust_scores")
    if rows:
        return rows
    return list(_scores.values())


@router.get("/trust-scores")
def trust_scores():
    return workers()


@router.get("/live/history")
def live_history():
    return list(reversed(_history[-100:])) or _read("trust_score_history", "created_at")


@router.get("/clients")
def clients():
    return _read("clients")


@router.get("/jobs")
def jobs():
    return list(_jobs.values()) or _read("jobs", "created_at")


@router.post("/jobs")
def create_job(job: JobCreate):
    import uuid
    row = job.model_dump()
    row["id"] = row["id"] or str(uuid.uuid4())
    row["status"] = "requested"
    _jobs[row["id"]] = row
    _insert("jobs", row)
    return row


@router.post("/reviews")
def create_review(review: ReviewCreate):
    row = review.model_dump()
    row["sentiment"] = 1.0 if row["stars"] >= 4 else (-1.0 if row["stars"] <= 2 else 0.0)
    _reviews.append(row)
    _insert("reviews", row)
    return row


@router.get("/reviews")
def reviews():
    return _reviews or _read("reviews", "created_at")


@router.post("/disputes")
def create_dispute(dispute: DisputeCreate):
    row = dispute.model_dump()
    row["status"] = "open"
    _disputes.append(row)
    _insert("disputes", row)
    return row


@router.get("/disputes")
def disputes():
    return _disputes or _read("disputes", "created_at")


@router.post("/scenario-runs")
def scenario_run(batch: SyncBatch):
    return sync_events(batch)


@router.get("/attack-test")
def attack_test():
    flat = {worker: sum(1 for event in _events.values() if event["worker_id"] == worker and event["payload"].get("client_confirmation")) for worker in _scores}
    tiered = {worker: score["score"] for worker, score in _scores.items()}
    return {"flat_average": flat, "tiered_scores": tiered, "workers": sorted(tiered, key=tiered.get, reverse=True)}
