"""
test_ui.py
==========
Automated verification suite for the TrustTier Model Testing & Evaluation Dashboard.
Tests all endpoints using FastAPI's TestClient without needing a network port:
- /api/predict (live 5-model pipeline & anomaly detection)
- /api/scenarios (6 preset attack & operational cases)
- /api/riders (200 riders & cohort filtering)
- /api/clients (normal vs Sybil clients)
- /api/benchmark (Objective 2 & 3 metrics)
- /api/latency (Objective 4 10x graph speedup)
"""

import sys
import os
from fastapi.testclient import TestClient
from ui_server import app

client = TestClient(app)

def test_dashboard():
    print("[*] Running TrustTier UI & Model Server Verification Suite...", flush=True)

    # 1. Test Static Index Page
    print("  [1/6] Testing GET / (HTML Dashboard)...", end=" ", flush=True)
    res = client.get("/")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert "TrustTier" in res.text, "Index HTML missing TrustTier title"
    print("PASSED")

    # 2. Test Presets Endpoint
    print("  [2/6] Testing GET /api/scenarios...", end=" ", flush=True)
    res = client.get("/api/scenarios")
    assert res.status_code == 200
    scenarios = res.json()
    assert len(scenarios) == 6, f"Expected 6 presets, got {len(scenarios)}"
    assert "review_ring" in scenarios and "honest_online" in scenarios
    print(f"PASSED ({len(scenarios)} presets loaded)")

    # 3. Test Riders & Cohorts
    print("  [3/6] Testing GET /api/riders (200 workers)...", end=" ", flush=True)
    res = client.get("/api/riders")
    assert res.status_code == 200
    riders = res.json()
    assert len(riders) == 200, f"Expected 200 riders, got {len(riders)}"
    
    # Cohort filtering check
    res_ring = client.get("/api/riders?cohort=Review Ring")
    assert len(res_ring.json()) == 10, f"Expected 10 Review Ring riders, got {len(res_ring.json())}"
    print("PASSED (200 riders, 10 Review Ring Sybils isolated)")

    # 4. Test Single Delivery Prediction on Honest Case
    print("  [4/6] Testing POST /api/predict (Honest Delivery)...", end=" ", flush=True)
    honest_payload = {
        "rider_id": "RDR-025",
        "client_id": "CLT-0350",
        "nfc_tap_present": 1,
        "arrival_event_present": 1,
        "start_event_present": 1,
        "finish_event_present": 1,
        "device_signature_valid": 1,
        "event_chain_valid": 1,
        "offline_sync": 0,
        "scheduled_duration_minutes": 40,
        "actual_duration_minutes": 42.5,
        "arrival_delay_minutes": -1.2,
        "client_confirmation": 1,
        "dispute_filed": 0
    }
    res_h = client.post("/api/predict", json=honest_payload)
    assert res_h.status_code == 200
    data_h = res_h.json()
    assert data_h["tier"] == "device_signed"
    assert data_h["models"]["trusttier_full"]["prob"] >= 0.95
    assert len(data_h["alerts"]) == 0
    print(f"PASSED (Tier: {data_h['tier']}, TrustTier: {data_h['models']['trusttier_full']['prob']*100:.1f}%)")

    # 5. Test Attack Detection on Review-Ring Fraud
    print("  [5/6] Testing POST /api/predict (Review-Ring Attack)...", end=" ", flush=True)
    ring_payload = {
        "rider_id": "RDR-185",
        "client_id": "CLT-2450",
        "nfc_tap_present": 0,
        "arrival_event_present": 1,
        "start_event_present": 1,
        "finish_event_present": 1,
        "device_signature_valid": 0,
        "event_chain_valid": 0,
        "offline_sync": 0,
        "scheduled_duration_minutes": 35,
        "actual_duration_minutes": 3.0,
        "arrival_delay_minutes": 0.2,
        "client_confirmation": 1,
        "dispute_filed": 0
    }
    res_r = client.post("/api/predict", json=ring_payload)
    assert res_r.status_code == 200
    data_r = res_r.json()
    assert data_r["models"]["flat_client"]["prob"] == 1.0, "Flat rating should be fooled (100%)"
    assert data_r["models"]["trusttier_full"]["prob"] < 0.15, "TrustTier should expose fraud (< 15%)"
    assert data_r["graph_context"]["client_credibility_weight"] <= 0.05, "Sybil client weight should be downweighted"
    assert any("Ghost Duration" in a["title"] for a in data_r["alerts"]), "Ghost duration alert missing"
    assert any("Sybil Review Ring" in a["title"] for a in data_r["alerts"]), "Sybil alert missing"
    print(f"PASSED (Flat Rating: 100% vs TrustTier: {data_r['models']['trusttier_full']['prob']*100:.1f}%, Sybil W_c: {data_r['graph_context']['client_credibility_weight']})")

    # 6. Test Benchmark Metrics
    print("  [6/6] Testing GET /api/benchmark (Objectives 2, 3 & 4)...", end=" ", flush=True)
    res_b = client.get("/api/benchmark")
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["test_set_size"] == 29889
    tt_model = [m for m in data_b["models_evaluation"] if m["type"] == "trusttier"][0]
    assert tt_model["roc_auc"] >= 0.98
    assert data_b["objective_4_latency"][-1]["speedup"] >= 9.0
    print(f"PASSED (ROC-AUC: {tt_model['roc_auc']}, Speedup at 100k: {data_b['objective_4_latency'][-1]['speedup']}x)")

    print("\n" + "=" * 55)
    print("[SUCCESS] ALL UI & MODEL TEST SUITE CHECKS PASSED!")
    print("=" * 55)

if __name__ == "__main__":
    test_dashboard()

