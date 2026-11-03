# TrustTier Dataset Data Dictionary

> **Project**: *TrustTier: Evidence-Weighted Belief Propagation for Offline Gig Worker Reliability Using Signed Hardware Badges and a Graph Database*  
> **Dataset**: `trusttier_deliveries.csv`  
> **Total Records**: 100,000  
> **Random Seed**: 42  
> **Target Problem**: Predict whether a gig delivery was actually completed (`ground_truth_completed`) in informal markets with intermittent connectivity (e.g., Gwadar and Turbat) using evidence-tiered hardware badges.

---

## 1. Field Reference Table

| Column Name | Data Type | Range / Domain | Model Input Status | Description & Domain Context |
| :--- | :---: | :---: | :---: | :--- |
| **`delivery_id`** | `str` | `DEL-000001` – `DEL-100000` | **No** (Identifier) | Unique identifier for each delivery job. 0 duplicates across 100,000 rows. Use as primary key or graph edge identifier. |
| **`rider_id`** | `str` | `RDR-001` – `RDR-200` | **No** (Graph Node / Grouping) | Identifier of the synthetic gig worker carrying the ESP32 hardware badge. 200 distinct riders partitioned into 5 calibrated cohorts for Objective 3 attack evaluation. |
| **`client_id`** | `str` | `CLT-0001` – `CLT-2500` | **No** (Graph Node / Grouping) | Identifier of the recipient/merchant client. Normal clients (`CLT-0001` to `CLT-2400`) vs. Sybil ring clients (`CLT-2401` to `CLT-2500`) who form a collusive biclique with `RDR-181`–`RDR-190`. |
| **`ground_truth_completed`** | `int` | `{0, 1}` | **Target Label** | Ground-truth completion status: `1` = delivery was legitimately completed; `0` = delivery failed, abandoned, or was fraudulent. Overall completion rate: **62.09%**. |
| **`nfc_tap_present`** | `int` | `{0, 1}` | **Yes** (Model Feature) | Binary indicator: `1` if an NFC tag tap at the client/merchant site was registered by the badge's NFC reader; `0` if absent or unread. Medium evidence tier ($LR(\\text{nfc}) = 1.8858 > 1.0$). |
| **`arrival_event_present`** | `int` | `{0, 1}` | **Yes** (Model Feature) | Lifecycle event flag: `1` if the rider recorded arrival at the delivery destination (timestamped by badge RTC or app). |
| **`start_event_present`** | `int` | `{0, 1}` | **Yes** (Model Feature) | Lifecycle event flag: `1` if the job start/pickup event was logged. |
| **`finish_event_present`** | `int` | `{0, 1}` | **Yes** (Model Feature) | Lifecycle event flag: `1` if the job finish/handover event was logged. |
| **`device_signature_valid`** | `int` | `{0, 1}` | **Yes** (Model Feature) | Cryptographic signature validity: `1` if digital signatures on the event payload match the ESP32 hardware badge's private device key; `0` if forged, unsigned, or corrupted. |
| **`event_chain_valid`** | `int` | `{0, 1}` | **Yes** (Model Feature) | Tamper-evident log integrity: `1` if the hash chain linking sequential events (`arrive` -> `start` -> `finish`) is unbroken and unaltered; `0` if entries were deleted, reordered, or edited. |
| **`offline_sync`** | `int` | `{0, 1}` | **Yes** (Model Feature) | Connectivity flag: `1` if events were buffered offline in ESP32 SPIFFS/flash due to dead zones in Gwadar/Turbat and synchronized later over Wi-Fi/Bluetooth; `0` if synced in near real-time. |
| **`scheduled_duration_minutes`** | `int` | `15` – `90` | **Yes** (Model Feature) | Expected route duration assigned by the dispatch platform based on transit distance and terrain. |
| **`actual_duration_minutes`** | `float` | `2.0` – `139.9` | **Yes** (Model Feature) | Elapsed duration between initial event and final event. Suspiciously fast durations (e.g. 2–5 mins) characterize ghost NFC check-ins and collusive rings. |
| **`arrival_delay_minutes`** | `float` | `-57.8` – `114.9` | **Yes** (Model Feature) | Punctuality metric: difference between arrival time and scheduled arrival time. Negative values indicate early arrival; large positive values indicate delays or abandoned routes. |
| **`client_confirmation`** | `int` | `{0, 1}` | **Yes** (Model Feature) | Client acknowledgement: `1` if recipient confirmed receipt via SMS/app; `0` otherwise. Note: Collusive clients confirm fake deliveries (`client_confirmation = 1` while `ground_truth_completed = 0`). |
| **`dispute_filed`** | `int` | `{0, 1}` | **Yes** (Model Feature) | Complaint flag: `1` if a customer dispute or missing package ticket was lodged. ~1.2% false disputes occur on honest jobs due to customer error. |
| **`review_ring_suspected`** | `int` | `{0, 1}` | **Yes** (Model Feature) | Platform-level graph anomaly signal: `1` if network graph analytics (community detection, dense bipartite subgraphs, reciprocal rating rings) flagged the transaction. |
| **`evidence_tier`** | `str` | `device_signed`, `nfc`, `self_reported`, `mixed` | **No** (Evaluation Metadata) | Qualitative evidence hierarchy defined in the TrustTier proposal: `device_signed` ($LR \\approx 48.95$), `nfc` ($LR \\approx 1.89$), `mixed` ($LR \\approx 0.25$), `self_reported` ($LR \\approx 0.09$). **Exclude from model input** to prevent leakage. |
| **`scenario_type`** | `str` | 8 scenario classes | **No** (Evaluation Metadata) | Underlying data generation archetype. Used for slice-based error analysis, fairness evaluation, and attack resilience testing. **Strictly exclude from model input**. |

---

## 2. Model Input Guidance

### Recommended Features for ML Models (13 Features)
```python
FEATURE_COLS = [
    "nfc_tap_present",
    "arrival_event_present",
    "start_event_present",
    "finish_event_present",
    "device_signature_valid",
    "event_chain_valid",
    "offline_sync",
    "scheduled_duration_minutes",
    "actual_duration_minutes",
    "arrival_delay_minutes",
    "client_confirmation",
    "dispute_filed",
    "review_ring_suspected",
]

TARGET_COL = "ground_truth_completed"
```

### Graph & Grouping Columns
- `delivery_id`: Edge / transaction identifier.
- `rider_id`: Worker node in the TrustTier graph (200 unique workers).
- `client_id`: Client / merchant node in the TrustTier graph (2,500 unique clients).

### Evaluation-Only Metadata (Excluded from Features)
- `evidence_tier`: Directly reflects the physical tier used in TrustTier belief propagation ($LR(\text{self}) < LR(\text{mixed}) < 1.0 < LR(\text{nfc}) < LR(\text{signed})$). Exclude during model training; use in evaluation to compare performance across evidence tiers.
- `scenario_type`: Ground truth scenario classification. Exclude during model training; use in slice analysis to measure model recall on adversarial attacks (e.g., ghost check-ins vs review rings).

---

## 3. Bayesian Evidence Tiers & Likelihood Ratios

The dataset satisfies the theoretical Bayesian inequality:
$$LR(\text{self}) < LR(\text{mixed}) < 1.0 < LR(\text{nfc}) < LR(\text{signed})$$

| Evidence Tier (`evidence_tier`) | Completed Rate | $LR(\text{tier})$ | Interpretation |
| :--- | :---: | :---: | :--- |
| **`self_reported`** | 13.45% | **0.0949** | Strong negative evidence ($LR < 1.0$). Worker self-reported via app without hardware proof. |
| **`mixed`** | 28.90% | **0.2481** | Negative evidence ($LR < 1.0$). Inconsistent crypto state, broken chain, or partial lifecycle. |
| **`nfc`** | 75.54% | **1.8858** | **Positive evidence ($LR > 1.0$)**. Physical client-site NFC tap verified intact without ESP32 crypto badge. |
| **`device_signed`** | 98.77% | **48.9500** | **Strong cryptographic proof ($LR \gg 1.0$)**. ESP32 device-signed payload and unbroken tamper-evident event chain. |

---

## 4. Rider Cohort Architecture for Objective 3 (Attack Test)

The 200 riders are partitioned into 5 cohorts designed to test whether TrustTier's evidence-weighted graph belief propagation resists adversarial manipulation better than flat star ratings:

| Cohort | Rider IDs | Count | True Completion | Flat Rating (Client Confirm) | Dispute Rate | Objective 3 Role |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Honest Veterans** | `RDR-001`–`RDR-130` | 130 | 80.91% | 75.64% | 13.99% | Baseline honest workforce with high badge compliance. |
| **Remote Workers** | `RDR-131`–`RDR-160` | 30 | 81.47% | 71.78% | 15.58% | Honest workers operating in dead-zones (Gwadar/Turbat outskirts); frequent offline syncs. |
| **Glitched Hardware** | `RDR-161`–`RDR-180` | 20 | 77.04% | 66.56% | 16.28% | Honest workers whose badges experienced dead batteries or NFC read errors. Protected by TrustTier. |
| **Review-Ring Sybils** | `RDR-181`–`RDR-190` | 10 | **6.00%** | **95.53%** | 1.69% | **Colluders who fool flat rating systems** with 95.5% fake confirmations from Sybil clients `CLT-2401`–`CLT-2500`. Exposed by TrustTier biclique detection and duration checks. |
| **Ghost Attackers** | `RDR-191`–`RDR-200` | 10 | **3.42%** | **6.85%** | 72.71% | Opportunistic attackers who attempt ghost NFC taps, app self-reports, or tampered chains against real clients. |

---

## 5. Scenario Catalog (`scenario_type`)

| Scenario Name | Description | True Completion | Key Behavioral Pattern |
| :--- | :--- | :---: | :--- |
| **`honest_verified_complete`** | Genuine delivery with full badge compliance. | ~99.5% | Valid signature, intact chain, NFC tap present, realistic transit time. |
| **`offline_delayed_sync_complete`** | Honest delivery completed in remote coverage dead-zone (Gwadar/Turbat outskirts). | ~99.0% | `offline_sync = 1`, all crypto logs verify once synced, slightly elevated delay. |
| **`glitched_hardware_complete`** | Genuine delivery where badge battery died or NFC tag unreadable. | ~96.0% | Low NFC tap presence, incomplete finish event, but confirmed by client. |
| **`abandoned_or_failed_incomplete`** | Delivery aborted due to breakdown, wrong address, or cancellation. | ~1.5% | Arrived or started, but no finish; high arrival delay; high dispute rate. |
| **`fake_nfc_ghost_checkin_incomplete`** | Cloned/quick NFC tap without leaving parcel. | ~2.0% | NFC tap present but broken lifecycle events; actual duration abnormally low (2–7 mins); high disputes. |
| **`forged_self_reported_incomplete`** | Worker claims completion in phone app without hardware badge. | ~5.0% | `device_signature_valid = 0`, `event_chain_valid = 0`, high dispute rate. |
| **`tampered_badge_broken_chain_incomplete`** | Replay attack, edited timestamps, or corrupted SPIFFS flash. | ~3.0% | Invalid signature, broken hash chain (`event_chain_valid = 0`). |
| **`collusive_review_ring`** | Worker and client collude to farm ratings/payouts. | ~6.0% | `client_confirmation = 1`, 0 disputes, duration artificially round or tiny, high graph flag. |

---

## 6. Hardware Realism & Context Notes
- **Motion Sensor Part**: As requested by the user, the optional MPU6050 accelerometer/gyroscope motion sensor feature is **completely excluded** from this dataset.
- **Noise & Non-Determinism**: No single feature has a correlation $> 0.68$ with `ground_truth_completed`. Models must learn multi-modal interactions (e.g., combining duration anomalies with client confirmation and event chains) to accurately classify deliveries.
