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
