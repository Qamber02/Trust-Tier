"""Live ingestion and demo persistence for signed TrustTier badge events."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api")
_lock = threading.RLock()
_events: dict[str, dict[str, Any]] = {}
_rejections: list[dict[str, Any]] = []
_devices: dict[str, dict[str, Any]] = {}
_scores: dict[str, dict[str, Any]] = {}
_history: list[dict[str, Any]] = []
_disputes: list[dict[str, Any]] = []
_reviews: list[dict[str, Any]] = []
_jobs: dict[str, dict[str, Any]] = {}
_job_activity: list[dict[str, Any]] = []

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


class RiderJobAction(BaseModel):
    worker_id: str
    action: str


class CustomerConfirmation(BaseModel):
    client_id: str
    stars: int = Field(ge=1, le=5)
    body: str = Field(default="", max_length=2000)


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


def _log_job_activity(job_id: str, actor_role: str, actor_id: str,
                      action: str, details: dict[str, Any] | None = None) -> None:
    row = {"job_id": job_id, "actor_role": actor_role, "actor_id": actor_id,
           "action": action, "details": details or {},
           "created_at": datetime.now(timezone.utc).isoformat()}
    _job_activity.append(row)
    try:
        _insert("job_activity", row)
    except Exception:
        # Keeps the API demo usable until migration 003 has been applied.
        pass


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
    old = _scores.get(worker_id)
    if old is None:
        client = _client()
        if client:
            found = client.table("trust_scores").select("*").eq("worker_id", worker_id).limit(1).execute().data
            old = found[0] if found else None
    old = old or {"worker_id": worker_id, "score": PRIOR, "evidence_counts": {"self": 0, "nfc": 0, "signed": 0}}
    previous = float(old["score"])
    posterior_odds = (previous / (1 - previous)) * LIKELIHOOD[event["evidence_tier"]]
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


def _propagate_to_neighbors(worker_id: str, client_id: str | None, before: float, after: float, event: dict[str, Any]) -> None:
    """Propagate a decayed fraction of a worker's log-odds change across shared-client edges."""
    if not client_id:
        return
    import math
    delta = math.log(after / (1 - after)) - math.log(before / (1 - before))
    neighbors = {e["worker_id"] for e in _events.values()
                 if e.get("verified") and e.get("client_id") == client_id
                 and e.get("worker_id") != worker_id}
    for neighbor in neighbors:
        row = _scores.get(neighbor, {"worker_id": neighbor, "score": PRIOR,
                                     "evidence_counts": {"self": 0, "nfc": 0, "signed": 0}})
        old_score = float(row["score"])
        log_odds = math.log(old_score / (1 - old_score)) + 0.35 * delta
        new_score = 1 / (1 + math.exp(-max(-20, min(20, log_odds))))
        row.update(score=new_score, updated_at=datetime.now(timezone.utc).isoformat())
        _scores[neighbor] = row
        history = {"worker_id": neighbor, "event_id": event["id"], "previous_score": old_score,
                   "score": new_score, "evidence_tier": event["evidence_tier"]}
        _history.append(history)
        _save("trust_scores", row)
        _insert("trust_score_history", history)
        try:
            _insert("edges", {"src_id": worker_id, "dst_id": neighbor,
                              "type": "shared_client", "weight": 0.35})
        except Exception:
            pass


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
            if reason:
                rejection = {"event_id": model.id, "device_id": model.device_id,
                             "worker_id": model.worker_id, "reason": reason,
                             "event_payload": event}
                _rejections.append(rejection)
                try:
                    _insert("event_rejections", rejection)
                except Exception:
                    pass
            score_change = None
            if reason is None:
                device["last_hash"] = model.hash
                device["last_seen_at"] = event["synced_at"]
                _devices[model.device_id] = device
                _save("devices", device)
                before, after = _apply_score(model.worker_id, event)
                _propagate_to_neighbors(model.worker_id, model.client_id, before, after, event)
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
    rows = sorted(_events.values(), key=lambda e: e.get("synced_at", ""), reverse=True)[:100]
    return rows or _read("events", "synced_at")


@router.get("/live/rejections")
def live_rejections():
    return list(reversed(_rejections[-100:])) or _read("event_rejections", "created_at")


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


@router.get("/graph")
def graph_edges():
    rows = [e for e in _events.values() if e.get("verified") and e.get("client_id")]
    return [{"src_id": row["worker_id"], "dst_id": row["client_id"], "type": "worker-client", "weight": 1.0}
            for row in rows[-100:]] or _read("edges")


@router.get("/clients")
def clients():
    return _read("clients")


@router.get("/jobs")
def jobs(worker_id: str | None = None, status: str | None = None,
         client_id: str | None = None,
         limit: int = Query(default=100, ge=1, le=500)):
    client = _client()
    if client:
        query = client.table("jobs").select("*").order("updated_at", desc=True).limit(limit)
        if worker_id:
            query = query.eq("worker_id", worker_id)
        if status:
            query = query.eq("status", status)
        if client_id:
            query = query.eq("client_id", client_id)
        return query.execute().data or []
    rows = list(_jobs.values())
    if worker_id:
        rows = [row for row in rows if row.get("worker_id") == worker_id]
    if status:
        rows = [row for row in rows if row.get("status") == status]
    if client_id:
        rows = [row for row in rows if row.get("client_id") == client_id]
    return rows[:limit]


@router.post("/jobs")
def create_job(job: JobCreate):
    import uuid
    row = job.model_dump()
    row["id"] = row["id"] or str(uuid.uuid4())
    row["status"] = "requested"
    _jobs[row["id"]] = row
    _insert("jobs", row)
    _log_job_activity(row["id"], "customer", row["client_id"], "requested")
    return row


@router.post("/jobs/{job_id}/actions")
def rider_job_action(job_id: str, action: RiderJobAction):
    allowed = {"accepted", "arrived", "started", "finished", "declined"}
    if action.action not in allowed:
        raise HTTPException(422, f"action must be one of {sorted(allowed)}")
    client = _client()
    if client:
        found = client.table("jobs").select("*").eq("id", job_id).limit(1).execute().data
        if not found:
            raise HTTPException(404, "job not found")
        row = found[0]
        if row["worker_id"] != action.worker_id:
            raise HTTPException(403, "job is assigned to another worker")
    else:
        row = _jobs.get(job_id)
        if not row:
            raise HTTPException(404, "job not found")
        if row.get("worker_id") != action.worker_id:
            raise HTTPException(403, "job is assigned to another worker")

    if action.action in {"accepted", "declined"} and row["status"] != "requested":
        raise HTTPException(409, "only a waiting request can be accepted or declined")
    status = ("cancelled" if action.action == "declined" else
              "in_progress" if action.action in {"accepted", "arrived", "started"} else
              "awaiting_confirm")
    row.update(status=status, updated_at=datetime.now(timezone.utc).isoformat(),
               last_rider_action=action.action)
    # Job status is persisted; the action label is response metadata, not badge proof.
    if client:
        client.table("jobs").update({"status": status, "updated_at": row["updated_at"]}).eq("id", job_id).execute()
    _jobs[job_id] = row
    _log_job_activity(job_id, "rider", action.worker_id, action.action)
    return row


@router.post("/jobs/{job_id}/confirm")
def confirm_job(job_id: str, confirmation: CustomerConfirmation):
    client = _client()
    if client:
        found = client.table("jobs").select("*").eq("id", job_id).limit(1).execute().data
        if not found:
            raise HTTPException(404, "job not found")
        job = found[0]
    else:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "job not found")
    if job["client_id"] != confirmation.client_id:
        raise HTTPException(403, "job belongs to another customer")
    if job["status"] != "awaiting_confirm":
        raise HTTPException(409, "rider must mark the delivery finished before confirmation")
    review = {"job_id": job_id, "worker_id": job["worker_id"],
              "client_id": confirmation.client_id, "stars": confirmation.stars,
              "body": confirmation.body,
              "sentiment": 1.0 if confirmation.stars >= 4 else (-1.0 if confirmation.stars <= 2 else 0.0)}
    try:
        _insert("reviews", review)
        _reviews.append(review)
        job.update(status="completed", updated_at=datetime.now(timezone.utc).isoformat())
        if client:
            client.table("jobs").update({"status": "completed", "updated_at": job["updated_at"]}).eq("id", job_id).execute()
        _jobs[job_id] = job
        _log_job_activity(job_id, "customer", confirmation.client_id, "confirmed",
                          {"stars": confirmation.stars, "body": confirmation.body})
    except Exception as exc:
        raise HTTPException(409, "confirmation could not be saved; check for an existing review") from exc
    return {"confirmed": True, "job": job, "review": review}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, client_id: str = Query(...)):
    client = _client()
    if client:
        found = client.table("jobs").select("*").eq("id", job_id).limit(1).execute().data
        if not found:
            raise HTTPException(404, "job not found")
        job = found[0]
    else:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "job not found")
    if job["client_id"] != client_id:
        raise HTTPException(403, "job belongs to another customer")
    if job["status"] != "requested":
        raise HTTPException(409, "only a waiting request can be cancelled")
    job.update(status="cancelled", updated_at=datetime.now(timezone.utc).isoformat())
    if client:
        client.table("jobs").update({"status": "cancelled", "updated_at": job["updated_at"]}).eq("id", job_id).execute()
    _jobs[job_id] = job
    _log_job_activity(job_id, "customer", client_id, "cancelled")
    return job


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
    client = _client()
    if client:
        found = client.table("jobs").select("worker_id,client_id").eq("id", row["job_id"]).limit(1).execute().data
        if not found:
            raise HTTPException(404, "job not found")
        if found[0]["client_id"] != row["client_id"] or found[0]["worker_id"] != row["worker_id"]:
            raise HTTPException(403, "dispute parties do not match the job")
    elif row["job_id"] in _jobs:
        job = _jobs[row["job_id"]]
        if job["client_id"] != row["client_id"] or job["worker_id"] != row["worker_id"]:
            raise HTTPException(403, "dispute parties do not match the job")
    _disputes.append(row)
    _insert("disputes", row)
    if client:
        client.table("jobs").update({"status": "disputed", "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", row["job_id"]).execute()
    if row["job_id"] in _jobs:
        _jobs[row["job_id"]].update(status="disputed", updated_at=datetime.now(timezone.utc).isoformat())
    _log_job_activity(row["job_id"], "customer", row["client_id"], "disputed",
                      {"reason": row["reason"]})
    return row


@router.get("/job-activity")
def job_activity(limit: int = Query(default=100, ge=1, le=500)):
    client = _client()
    if client:
        try:
            return client.table("job_activity").select("*").order(
                "created_at", desc=True).limit(limit).execute().data or []
        except Exception:
            pass
    return list(reversed(_job_activity[-limit:]))


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


@router.get("/config/public")
def public_config():
    # Publish only Supabase's public URL/anon key. The service-role key is never returned.
    return {"supabase_url": os.getenv("SUPABASE_URL", ""), "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", "")}
