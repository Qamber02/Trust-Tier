import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import trusttier_live as live
from tools.badge_simulator import make_event


def _setup(monkeypatch, device_id="TEST-DEVICE"):
    monkeypatch.setattr(live, "_client", lambda: None)
    live._events.clear()
    live._devices.clear()
    live._scores.clear()
    live._history.clear()
    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    live.register_device(live.DeviceRegistration(
        id=device_id, worker_id="RDR-TEST", public_key=base64.b64encode(public_key).decode()))
    return key


def test_signed_batch_updates_tier_scores_and_deduplicates(monkeypatch):
    key = _setup(monkeypatch)
    first = make_event(key, "TEST-DEVICE", "RDR-TEST", None, "arrive", "nfc", "")
    second = make_event(key, "TEST-DEVICE", "RDR-TEST", None, "finish", "signed", first["hash"])

    result = live.sync_events(live.SyncBatch(events=[first, second]))
    assert result["accepted"] == 2
    assert result["rejected"] == 0
    assert result["results"][1]["score_change"]["after"] > result["results"][0]["score_change"]["after"]
    duplicate = live.sync_events(live.SyncBatch(events=[first]))
    assert duplicate["rejected"] == 1
    assert "duplicate" in duplicate["results"][0]["reason"]


def test_tampered_payload_is_retained_as_rejected(monkeypatch):
    key = _setup(monkeypatch, "TAMPER-DEVICE")
    event = make_event(key, "TAMPER-DEVICE", "RDR-TEST", None, "arrive", "signed", "")
    event["payload"]["altered"] = True
    result = live.sync_events(live.SyncBatch(events=[event]))
    assert result["rejected"] == 1
    assert "hash mismatch" in result["results"][0]["reason"]
    assert live._events[event["id"]]["verified"] is False


def test_rider_workflow_and_customer_confirmation_are_separate(monkeypatch):
    monkeypatch.setattr(live, "_client", lambda: None)
    live._jobs.clear()
    live._job_activity.clear()
    job = live.create_job(live.JobCreate(
        worker_id="RDR-TEST", client_id="CLT-TEST",
        title="Separate rider and customer workflow", address="Test street"))

    for action in ("accepted", "arrived", "started", "finished"):
        live.rider_job_action(job["id"], live.RiderJobAction(
            worker_id="RDR-TEST", action=action))

    assert live._jobs[job["id"]]["status"] == "awaiting_confirm"
    confirmation = live.confirm_job(job["id"], live.CustomerConfirmation(
        client_id="CLT-TEST", stars=5, body="Received"))
    assert confirmation["confirmed"] is True
    assert live._jobs[job["id"]]["status"] == "completed"
    assert [row["actor_role"] for row in live._job_activity] == [
        "customer", "rider", "rider", "rider", "rider", "customer"]
    assert [row["action"] for row in live._job_activity[-2:]] == [
        "finished", "confirmed"]


def test_devices_and_comparison_endpoints(monkeypatch):
    key = _setup(monkeypatch, "ESP32-TEST-01")
    event = make_event(key, "ESP32-TEST-01", "RDR-TEST", None, "finish", "signed", "")
    live.sync_events(live.SyncBatch(events=[event]))

    devices = live.list_devices()
    assert len(devices) == 1
    assert devices[0]["id"] == "ESP32-TEST-01"
    assert devices[0]["has_chain"] is True
    assert "public_key" not in devices[0]

    comp = live.system_comparison()
    assert len(comp["dimensions"]) == 5
    assert comp["live_summary"]["devices_registered"] == 1
    assert comp["live_summary"]["verified_events"] == 1
    assert comp["worker_deltas"][0]["worker_id"] == "RDR-TEST"
