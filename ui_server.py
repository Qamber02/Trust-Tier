"""
ui_server.py
============
FastAPI backend server for the TrustTier Model Testing & Evaluation Dashboard.
Provides:
- Unpickling compatibility for Kaggle-exported scikit-learn models
- Real-time 5-model single delivery prediction & anomaly risk detection
- 200-Rider 5-cohort attack resistance lookup & leaderboard
- Objective 3 & 4 benchmark metrics and latency results
- Web dashboard serving at http://127.0.0.1:8000
"""

import sys
import os
import time
import joblib
import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from trusttier_live import router as live_router

# Unpickling compatibility bridge for Kaggle-trained scikit-learn models
try:
    import sklearn._loss._loss
    sys.modules['_loss'] = sklearn._loss._loss
except ImportError:
    pass

# Initialize FastAPI application
app = FastAPI(
    title="TrustTier Model Testing & Evaluation Dashboard",
    description="Evidence-Weighted Graph Belief Propagation & Hardware Badge Verification Suite",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(live_router)

# Load data and trained models
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_PATH = os.path.join(BASE_DIR, "trusttier_v2_models.joblib")
RIDERS_PATH = os.path.join(BASE_DIR, "trusttier_v2_rider_scores.csv")
CLIENTS_PATH = os.path.join(BASE_DIR, "trusttier_v2_client_weights.csv")
STATIC_DIR = os.path.join(BASE_DIR, "static")

if not os.path.exists(MODELS_PATH):
    raise FileNotFoundError(f"Missing {MODELS_PATH}. Run trusttier_kaggle_pipeline.py first.")

print("[*] Loading TrustTier v2 models & graph artifacts...", flush=True)
models_bundle = joblib.load(MODELS_PATH)
hw_model = models_bundle['hw_model']
trusttier_clf = models_bundle['trusttier_clf']
tier_lr_map = models_bundle['tier_lr_map']

df_riders = pd.read_csv(RIDERS_PATH).set_index('rider_id')
df_clients = pd.read_csv(CLIENTS_PATH).set_index('client_id')

prior_p = 0.6209
prior_odds = prior_p / (1.0 - prior_p)
log_prior_odds = float(np.log(prior_odds))

print(f"[+] Loaded HW Model ({len(hw_model.feature_names_in_)} feats), TrustTier CLF ({len(trusttier_clf.feature_names_in_)} feats)")
print(f"[+] Loaded {len(df_riders)} Riders and {len(df_clients)} Clients.", flush=True)


# Pydantic schema for delivery inputs
class DeliveryInput(BaseModel):
    rider_id: str = Field("RDR-001", description="Rider identifier RDR-001 to RDR-200")
    client_id: str = Field("CLT-0001", description="Client identifier CLT-0001 to CLT-2500")
    nfc_tap_present: int = Field(1, ge=0, le=1)
    arrival_event_present: int = Field(1, ge=0, le=1)
    start_event_present: int = Field(1, ge=0, le=1)
    finish_event_present: int = Field(1, ge=0, le=1)
    device_signature_valid: int = Field(1, ge=0, le=1)
    event_chain_valid: int = Field(1, ge=0, le=1)
    offline_sync: int = Field(0, ge=0, le=1)
    scheduled_duration_minutes: int = Field(45, ge=10, le=120)
    actual_duration_minutes: float = Field(42.0, ge=1.0, le=240.0)
    arrival_delay_minutes: float = Field(2.0, ge=-60.0, le=180.0)
    client_confirmation: int = Field(1, ge=0, le=1)
    dispute_filed: int = Field(0, ge=0, le=1)


# Preset Scenarios Catalog
PRESET_SCENARIOS = {
    "honest_online": {
        "title": "Honest Online Delivery",
        "category": "Legitimate",
        "description": "Standard delivery in Gwadar city with full ESP32 cryptographic badge compliance and verified client NFC tap.",
        "badge_color": "emerald",
        "inputs": {
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
    },
    "offline_deadzone": {
        "title": "Gwadar Port Offline Sync",
        "category": "Legitimate",
        "description": "Legitimate delivery completed in a 2G/coverage dead-zone. Buffered in ESP32 flash and synced on return with intact cryptographic chain.",
        "badge_color": "sky",
        "inputs": {
            "rider_id": "RDR-140",
            "client_id": "CLT-1280",
            "nfc_tap_present": 1,
            "arrival_event_present": 1,
            "start_event_present": 1,
            "finish_event_present": 1,
            "device_signature_valid": 1,
            "event_chain_valid": 1,
            "offline_sync": 1,
            "scheduled_duration_minutes": 65,
            "actual_duration_minutes": 71.0,
            "arrival_delay_minutes": 6.5,
            "client_confirmation": 1,
            "dispute_filed": 0
        }
    },
    "glitched_badge": {
        "title": "Glitched Badge (Honest Worker)",
        "category": "Edge-Case",
        "description": "Honest worker whose badge battery died mid-job. Pure hardware model penalizes, but TrustTier graph BP rescues the worker.",
        "badge_color": "amber",
        "inputs": {
            "rider_id": "RDR-170",
            "client_id": "CLT-0915",
            "nfc_tap_present": 0,
            "arrival_event_present": 1,
            "start_event_present": 1,
            "finish_event_present": 0,
            "device_signature_valid": 0,
            "event_chain_valid": 0,
            "offline_sync": 1,
            "scheduled_duration_minutes": 50,
            "actual_duration_minutes": 48.0,
            "arrival_delay_minutes": 3.0,
            "client_confirmation": 1,
            "dispute_filed": 0
        }
    },
    "review_ring": {
        "title": "Collusive Review Ring Fraud",
        "category": "Adversarial",
        "description": "Colluding rider RDR-185 and Sybil client CLT-2450 fabricate orders. Flat rating gives 100%, but TrustTier exposes as fraud.",
        "badge_color": "rose",
        "inputs": {
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
    },
    "ghost_checkin": {
        "title": "Ghost NFC Check-In Attack",
        "category": "Adversarial",
        "description": "Rider quickly taps a cloned NFC tag from a motorcycle without delivering the parcel. Customer files a dispute.",
        "badge_color": "purple",
        "inputs": {
            "rider_id": "RDR-195",
            "client_id": "CLT-0520",
            "nfc_tap_present": 1,
            "arrival_event_present": 1,
            "start_event_present": 0,
            "finish_event_present": 1,
            "device_signature_valid": 0,
            "event_chain_valid": 0,
            "offline_sync": 0,
            "scheduled_duration_minutes": 55,
            "actual_duration_minutes": 4.5,
            "arrival_delay_minutes": 1.0,
            "client_confirmation": 0,
            "dispute_filed": 1
        }
    },
    "forged_app": {
        "title": "Forged Phone App Self-Report",
        "category": "Adversarial",
        "description": "Worker leaves hardware badge at home and manually clicks 'arrived' and 'delivered' in smartphone app without physical proof.",
        "badge_color": "orange",
        "inputs": {
            "rider_id": "RDR-198",
            "client_id": "CLT-1640",
            "nfc_tap_present": 0,
            "arrival_event_present": 1,
            "start_event_present": 1,
            "finish_event_present": 1,
            "device_signature_valid": 0,
            "event_chain_valid": 0,
            "offline_sync": 0,
            "scheduled_duration_minutes": 45,
            "actual_duration_minutes": 38.0,
            "arrival_delay_minutes": 18.5,
            "client_confirmation": 0,
            "dispute_filed": 1
        }
    }
}


def compute_prediction_pipeline(data: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.perf_counter()
    nfc = int(data.get('nfc_tap_present', 1))
    arrival = int(data.get('arrival_event_present', 1))
    start = int(data.get('start_event_present', 1))
    finish = int(data.get('finish_event_present', 1))
    sig = int(data.get('device_signature_valid', 1))
    chain = int(data.get('event_chain_valid', 1))
    offline = int(data.get('offline_sync', 0))
    sched = max(int(data.get('scheduled_duration_minutes', 45)), 1)
    actual = max(float(data.get('actual_duration_minutes', 42.0)), 0.1)
    delay = float(data.get('arrival_delay_minutes', 2.0))
    confirm = int(data.get('client_confirmation', 1))
    dispute = int(data.get('dispute_filed', 0))
    r_id = str(data.get('rider_id', 'RDR-001')).strip()
    c_id = str(data.get('client_id', 'CLT-0001')).strip()

    # Evidence tier derivation
    if sig == 1 and chain == 1 and arrival == 1 and finish == 1:
        tier = 'device_signed'
    elif nfc == 1 and arrival == 1 and finish == 1 and not (sig == 1 and chain == 1):
        tier = 'nfc'
    elif nfc == 0 and sig == 0 and chain == 0:
        tier = 'self_reported'
    else:
        tier = 'mixed'

    dur_ratio = actual / float(sched)
    is_ghost = 1 if dur_ratio < 0.25 else 0
    is_delay = 1 if delay > 20.0 else 0

    # Hardware Model Inference
    hw_row = pd.DataFrame([{
        'nfc_tap_present': nfc,
        'arrival_event_present': arrival,
        'start_event_present': start,
        'finish_event_present': finish,
        'device_signature_valid': sig,
        'event_chain_valid': chain,
        'offline_sync': offline,
        'duration_ratio': dur_ratio,
        'is_ghost_duration': is_ghost,
        'is_severe_delay': is_delay,
        'tier_device_signed': 1.0 if tier == 'device_signed' else 0.0,
        'tier_mixed': 1.0 if tier == 'mixed' else 0.0,
        'tier_nfc': 1.0 if tier == 'nfc' else 0.0,
        'tier_self_reported': 1.0 if tier == 'self_reported' else 0.0,
    }])[hw_model.feature_names_in_]

    p_hw = float(np.clip(hw_model.predict_proba(hw_row)[0, 1], 1e-4, 1.0 - 1e-4))
    hw_log_lr = float(np.log(p_hw / (1.0 - p_hw)) - log_prior_odds)

    # Pure Bayesian Evidence-Tier Odds Updating
    pure_tier_log_lr = float(np.log(tier_lr_map[tier]))
    pure_tier_prob = float(1.0 / (1.0 + np.exp(-(log_prior_odds + pure_tier_log_lr))))

    # Graph Context Lookup
    bp_rider_prob = float(df_riders.loc[r_id, 'trusttier_bp_prob']) if r_id in df_riders.index else prior_p
    bp_client_weight = float(df_clients.loc[c_id, 'credibility_weight']) if c_id in df_clients.index else 1.0

    bp_edge_log_lr = float(
        0.65 * hw_log_lr +
        1.80 * confirm * (bp_client_weight ** 2) -
        1.60 * dispute -
        1.40 * confirm * (1.0 - bp_client_weight)
    )

    # TrustTier Stage 3 Full Classifier Inference
    clf_row = pd.DataFrame([{
        'nfc_tap_present': nfc,
        'arrival_event_present': arrival,
        'start_event_present': start,
        'finish_event_present': finish,
        'device_signature_valid': sig,
        'event_chain_valid': chain,
        'offline_sync': offline,
        'duration_ratio': dur_ratio,
        'is_ghost_duration': is_ghost,
        'is_severe_delay': is_delay,
        'client_confirmation': confirm,
        'dispute_filed': dispute,
        'pure_tier_log_lr': pure_tier_log_lr,
        'hw_log_lr': hw_log_lr,
        'bp_rider_prob': bp_rider_prob,
        'bp_client_weight': bp_client_weight,
        'bp_edge_log_lr': bp_edge_log_lr,
        'tier_device_signed': 1.0 if tier == 'device_signed' else 0.0,
        'tier_mixed': 1.0 if tier == 'mixed' else 0.0,
        'tier_nfc': 1.0 if tier == 'nfc' else 0.0,
        'tier_self_reported': 1.0 if tier == 'self_reported' else 0.0,
    }])[trusttier_clf.feature_names_in_]

    p_full = float(trusttier_clf.predict_proba(clf_row)[0, 1])

    # Anomaly alerts
    alerts = []
    if is_ghost:
        alerts.append({
            "level": "error",
            "title": "Ghost Duration Anomaly",
            "detail": f"Actual duration ({actual:.1f}m) is only {dur_ratio*100:.1f}% of scheduled ({sched}m). Strongly indicates fraudulent check-in."
        })
    if is_delay:
        alerts.append({
            "level": "warning",
            "title": "Severe Arrival Delay",
            "detail": f"Worker arrived {delay:.1f} minutes behind schedule."
        })
    if chain == 0 and (arrival == 1 or finish == 1):
        alerts.append({
            "level": "error",
            "title": "Cryptographic Chain Tampered/Broken",
            "detail": "Sequential event hash chain does not verify against ESP32 badge RTC logs."
        })
    if bp_client_weight < 0.20:
        alerts.append({
            "level": "error",
            "title": "Client Sybil Review Ring Detected",
            "detail": f"Client {c_id} credibility weight is {bp_client_weight:.2f} (< 0.20), identified inside a dense collusive biclique."
        })
    elif bp_client_weight < 0.70:
        alerts.append({
            "level": "warning",
            "title": "Degraded Client Credibility",
            "detail": f"Client {c_id} credibility is downweighted to {bp_client_weight:.2f} due to frequent hardware contradictions."
        })

    rider_cohort = df_riders.loc[r_id, 'cohort'] if r_id in df_riders.index else "Unknown"

    return {
        "tier": tier,
        "empirical_lr": float(tier_lr_map[tier]),
        "models": {
            "naive_claim": {
                "name": "1. Naive Self-Reported Claim",
                "prob": float(finish),
                "badge": "finish_event_present",
                "description": "Assumes job is done if worker clicked finished."
            },
            "flat_client": {
                "name": "2. Flat Client Confirmation",
                "prob": float(confirm),
                "badge": "client_confirmation",
                "description": "Standard app star rating / customer confirmation."
            },
            "pure_tier": {
                "name": "3. Pure Evidence Tier (Bayesian LR)",
                "prob": round(pure_tier_prob, 4),
                "badge": f"LR({tier}) = {tier_lr_map[tier]:.2f}",
                "description": "Posterior odds updated strictly by hardware evidence tier."
            },
            "hardware_ml": {
                "name": "4. Hardware Badge ML (No Graph)",
                "prob": round(p_hw, 4),
                "badge": f"log-LR = {hw_log_lr:+.2f}",
                "description": "HistGradientBoosting on crypto flags and timing."
            },
            "trusttier_full": {
                "name": "5. TrustTier Graph BP + Hardware (Full)",
                "prob": round(p_full, 4),
                "badge": "Full Graph Defense",
                "description": "Complete system uniting tiered evidence and graph belief propagation."
            }
        },
        "graph_context": {
            "rider_id": r_id,
            "rider_cohort": rider_cohort,
            "rider_bp_prob": round(bp_rider_prob, 4),
            "client_id": c_id,
            "client_credibility_weight": round(bp_client_weight, 4),
            "edge_log_lr": round(bp_edge_log_lr, 3)
        },
        "timing_metrics": {
            "duration_ratio": round(dur_ratio, 3),
            "is_ghost_duration": bool(is_ghost),
            "is_severe_delay": bool(is_delay)
        },
        "engine_info": {
            "is_live_model": True,
            "model_file": "trusttier_v2_models.joblib",
            "model_type": type(trusttier_clf).__name__,
            "n_trees": len(trusttier_clf._predictors),
            "features_count": len(trusttier_clf.feature_names_in_),
            "inference_ms": round((time.perf_counter() - t0) * 1000, 2),
            "hw_model_trees": len(hw_model._predictors),
            "raw_input_vector": {k: (round(v, 4) if isinstance(v, (float, np.floating)) else int(v) if isinstance(v, (int, np.integer)) else v) for k, v in clf_row.iloc[0].to_dict().items()}
        },
        "alerts": alerts
    }


# API Endpoints
@app.post("/api/predict")
async def api_predict(delivery: DeliveryInput):
    return compute_prediction_pipeline(delivery.dict())


@app.get("/api/scenarios")
async def api_scenarios():
    return PRESET_SCENARIOS


@app.get("/api/riders")
async def api_riders(cohort: Optional[str] = None, search: Optional[str] = None):
    riders_data = df_riders.reset_index().to_dict(orient="records")
    if cohort and cohort != "all":
        riders_data = [r for r in riders_data if cohort.lower() in str(r.get("cohort", "")).lower()]
    if search:
        search_lower = search.lower()
        riders_data = [r for r in riders_data if search_lower in str(r.get("rider_id", "")).lower()]
    return riders_data


@app.get("/api/clients")
async def api_clients(limit: int = 100, sybil_only: bool = False):
    clients_df = df_clients.reset_index()
    if sybil_only:
        clients_df = clients_df[clients_df['credibility_weight'] < 0.20]
    return clients_df.head(limit).to_dict(orient="records")


@app.get("/api/benchmark")
async def api_benchmark():
    # Verified Held-Out Test Set (n = 29,889) and Objective 3 / 4 benchmarks
    return {
        "test_set_size": 29889,
        "models_evaluation": [
            {
                "model": "1. Naive Self-Reported (finish_event)",
                "roc_auc": 0.7192,
                "pr_auc": 0.7487,
                "f1": 0.8305,
                "accuracy": 76.74,
                "brier": 0.2326,
                "type": "baseline"
            },
            {
                "model": "2. Flat Client Confirmation Rating",
                "roc_auc": 0.8314,
                "pr_auc": 0.8393,
                "f1": 0.8786,
                "accuracy": 84.63,
                "brier": 0.1537,
                "type": "baseline"
            },
            {
                "model": "3. Pure Bayesian Evidence-Tier (LR only)",
                "roc_auc": 0.9214,
                "pr_auc": 0.9386,
                "f1": 0.8926,
                "accuracy": 87.07,
                "brier": 0.0996,
                "type": "bayesian"
            },
            {
                "model": "4. Hardware Badge ML (No Graph)",
                "roc_auc": 0.9825,
                "pr_auc": 0.9880,
                "f1": 0.9621,
                "accuracy": 95.31,
                "brier": 0.0379,
                "type": "ml"
            },
            {
                "model": "5. TrustTier Graph BP + Hardware (Full)",
                "roc_auc": 0.9865,
                "pr_auc": 0.9902,
                "f1": 0.9823,
                "accuracy": 97.80,
                "brier": 0.0205,
                "type": "trusttier"
            }
        ],
        "objective_3_attack_test": [
            {
                "method": "1. Naive Self-Reported Claim",
                "spearman_rho": 0.6051,
                "kendall_tau": 0.5002,
                "attacker_recall_20": 0.0,
                "ring_caught_20": 0.0,
                "ring_fooled_top10": 100.0,
                "glitched_fpr_20": 100.0
            },
            {
                "method": "2. Flat Client Confirmation",
                "spearman_rho": 0.4597,
                "kendall_tau": 0.3652,
                "attacker_recall_20": 50.0,
                "ring_caught_20": 0.0,
                "ring_fooled_top10": 100.0,
                "glitched_fpr_20": 50.0
            },
            {
                "method": "3. Pure Tier Log-LR (No Graph)",
                "spearman_rho": 0.8334,
                "kendall_tau": 0.6428,
                "attacker_recall_20": 100.0,
                "ring_caught_20": 100.0,
                "ring_fooled_top10": 0.0,
                "glitched_fpr_20": 0.0
            },
            {
                "method": "4. TrustTier Graph BP (Full)",
                "spearman_rho": 0.8846,
                "kendall_tau": 0.7144,
                "attacker_recall_20": 100.0,
                "ring_caught_20": 100.0,
                "ring_fooled_top10": 0.0,
                "glitched_fpr_20": 0.0
            }
        ],
        "objective_4_latency": [
            {"events": 10000, "sql_join_ms": 0.50, "graph_traversal_ms": 0.10, "speedup": 5.1},
            {"events": 50000, "sql_join_ms": 6.52, "graph_traversal_ms": 0.89, "speedup": 7.3},
            {"events": 100000, "sql_join_ms": 25.40, "graph_traversal_ms": 2.55, "speedup": 10.0}
        ]
    }


# Mount static directory for frontend
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>TrustTier API is running. index.html is being prepared...</h2>")


@app.get("/simple", response_class=HTMLResponse)
async def serve_simple():
    simple_file = os.path.join(STATIC_DIR, "simple.html")
    if os.path.exists(simple_file):
        with open(simple_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>Simple UI is being prepared...</h2>")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("ui_server:app", host="127.0.0.1", port=8000, reload=False)
