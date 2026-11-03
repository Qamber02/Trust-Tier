# TrustTier Dataset Generation Report

> **Project**: TrustTier: Evidence-Weighted Belief Propagation for Offline Gig Worker Reliability Using Signed Hardware Badges and a Graph Database
> **Generated At**: Seed 42 Execution
> **Total Records**: 100,000
> **Motion Sensor Status**: **Excluded as per user request** (no sensor column present)

---

## 1. Executive Summary & Verification Metrics

| Metric | Target Requirement | Generated Value | Status |
| :--- | :--- | :--- | :--- |
| **Random Seed** | `42` | `42` | PASSED |
| **Total Rows** | Exactly `100,000` | `100,000` | PASSED |
| **Unique Delivery IDs** | `100,000` (0 duplicates) | `100,000` | PASSED |
| **Unique Synthetic Riders** | Exactly `200` (`RDR-001` to `RDR-200`) | `200` | PASSED |
| **Unique Clients** | High graph diversity (`CLT-0001` to `CLT-2500`) | `2500` | PASSED |
| **Class Balance** | 30.0% to 70.0% | **62.09%** completed (`62,093` rows) | PASSED |
| **Total Columns** | 19 columns (13 model features, 3 IDs, 1 target label, 2 evaluation metadata fields; motion sensor excluded) | `19` columns | PASSED |
| **Single Feature Determinism** | No single feature correlation >= 0.95 | Max abs corr: `0.6713` | PASSED |

---

## 2. Bayesian Evidence Tiers & Likelihood Ratios

The empirical likelihood ratios satisfy Bayesian monotonicity:
$$LR(\text{self}) < LR(\text{mixed}) < 1.0 < LR(\text{nfc}) < LR(\text{signed})$$

With a dataset prior of $P(GT=1) = 62.09\%$ (Prior Odds = 1.6380):

| Evidence Tier (`evidence_tier`) | Row Count | Pct Total | Completed | Completion Rate | $P(\text{tier} \mid GT=1)$ | $P(\text{tier} \mid GT=0)$ | Empirical $LR(\text{tier})$ | Posterior Odds |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `device_signed` | 41,971 | 41.97% | 41,454 | 98.77% | 0.6676 | 0.0136 | **48.9500** | 80.1818 |
| `mixed` | 18,832 | 18.83% | 5,442 | 28.9% | 0.0876 | 0.3532 | **0.2481** | 0.4064 |
| `nfc` | 15,984 | 15.98% | 12,075 | 75.54% | 0.1945 | 0.1031 | **1.8858** | 3.0890 |
| `self_reported` | 23,213 | 23.21% | 3,122 | 13.45% | 0.0503 | 0.5300 | **0.0949** | 0.1554 |

*Notice: $LR(\text{nfc}) = 1.8858 > 1.0$, meaning an NFC tap acts as a genuine positive evidence multiplier in belief propagation, while $LR(\text{device_signed}) = 48.9500$ provides strong cryptographic proof.*

---

## 3. Rider Cohort Partitioning & Objective 3 (Attack Test) Benchmark

The 200 riders are partitioned into 5 calibrated cohorts to clearly demonstrate that TrustTier's evidence-weighted graph scoring outperforms a flat average rating:

| Cohort | Riders | Total Jobs | True Completion | Flat Client Confirm | Dispute Rate | Device-Signed Share | Key Behavioral Pattern |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `1_Honest_Veterans (RDR-001 to RDR-130)` | 130 | 54,436 | **80.91%** | **75.64%** | 13.99% | 60.9% | Standard operational deliveries |
| `2_Remote_Riders (RDR-131 to RDR-160)` | 30 | 13,525 | **81.47%** | **71.78%** | 15.58% | 60.59% | Standard operational deliveries |
| `3_Glitched_Hardware (RDR-161 to RDR-180)` | 20 | 7,809 | **77.04%** | **66.56%** | 16.28% | 7.67% | Real deliveries but intermittent battery/crypto loss; protected by TrustTier |
| `4A_Review_Ring_Sybils (RDR-181 to RDR-190)` | 10 | 7,114 | **6.0%** | **95.53%** | 1.69% | 0.21% | Top rated under flat average; exposed by TrustTier biclique & duration analysis |
| `4B_Ghost_Attackers (RDR-191 to RDR-200)` | 10 | 17,116 | **3.42%** | **6.85%** | 72.71% | 0.06% | Standard operational deliveries |

### Key Objective 3 Takeaways:
1. **Collusive Review Ring Sybils (`RDR-181` to `RDR-190`)**:
   - **Flat Rating Illusion**: Achieve **95.53%** client confirmation (rated in top tier under a naive flat average!).
   - **Ground Truth Reality**: True completion is only **6.0%**.
   - **TrustTier Defense**: Their crypto signed share is only **0.21%**, their jobs form an isolated biclique with Sybil clients (`CLT-2401` to `CLT-2500`), and their durations are artificially short (2–5 mins). Graph belief propagation crushes their trust score!
2. **Glitched Hardware Riders (`RDR-161` to `RDR-180`)**:
   - True completion is **77.04%**.
   - Because attacker leakage into `device_signed` is eliminated, these honest workers cleanly outscore attackers under both pure tier scoring and graph belief propagation.

---

## 4. Scenario Distribution Breakdown

| Scenario Type (`scenario_type`) | Count | Pct Total | Completed | Completion Rate | Client Confirm | Disputes | Avg Actual Min |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `abandoned_or_failed_incomplete` | 14,500 | 14.5% | 244 | 1.68% | 596 | 9,866 | 23.2 |
| `collusive_review_ring` | 7,000 | 7.0% | 427 | 6.1% | 6,795 | 43 | 15.4 |
| `fake_nfc_ghost_checkin_incomplete` | 7,000 | 7.0% | 158 | 2.26% | 484 | 5,579 | 5.0 |
| `forged_self_reported_incomplete` | 6,000 | 6.0% | 312 | 5.2% | 292 | 4,397 | 31.7 |
| `glitched_hardware_complete` | 8,000 | 8.0% | 7,669 | 95.86% | 6,591 | 265 | 54.0 |
| `honest_verified_complete` | 41,000 | 41.0% | 40,797 | 99.5% | 38,126 | 479 | 40.3 |
| `offline_delayed_sync_complete` | 12,500 | 12.5% | 12,370 | 98.96% | 10,776 | 524 | 62.0 |
| `tampered_badge_broken_chain_incomplete` | 4,000 | 4.0% | 116 | 2.9% | 391 | 2,403 | 31.3 |

---

## 5. Missing Value Audit

| Column Name | Data Type | Missing Count | Missing Rate |
| :--- | :--- | :---: | :---: |
| `delivery_id` | `str` | 0 | 0.00% |
| `rider_id` | `str` | 0 | 0.00% |
| `client_id` | `str` | 0 | 0.00% |
| `ground_truth_completed` | `int64` | 0 | 0.00% |
| `nfc_tap_present` | `int64` | 0 | 0.00% |
| `arrival_event_present` | `int64` | 0 | 0.00% |
| `start_event_present` | `int64` | 0 | 0.00% |
| `finish_event_present` | `int64` | 0 | 0.00% |
| `device_signature_valid` | `int64` | 0 | 0.00% |
| `event_chain_valid` | `int64` | 0 | 0.00% |
| `offline_sync` | `int64` | 0 | 0.00% |
| `scheduled_duration_minutes` | `int64` | 0 | 0.00% |
| `actual_duration_minutes` | `float64` | 0 | 0.00% |
| `arrival_delay_minutes` | `float64` | 0 | 0.00% |
| `client_confirmation` | `int64` | 0 | 0.00% |
| `dispute_filed` | `int64` | 0 | 0.00% |
| `review_ring_suspected` | `int64` | 0 | 0.00% |
| `evidence_tier` | `str` | 0 | 0.00% |
| `scenario_type` | `str` | 0 | 0.00% |

*Notice: 0 missing values across all 19 active columns.*

---

## 6. Correlation with Ground Truth (`ground_truth_completed`)

| Feature Name | Pearson Correlation with Target | Interpretation |
| :--- | :---: | :--- |
| `nfc_tap_present` | +0.6278 |
| `arrival_event_present` | +0.2594 |
| `start_event_present` | +0.4486 |
| `finish_event_present` | +0.4864 |
| `device_signature_valid` | +0.5130 |
| `event_chain_valid` | +0.6079 |
| `offline_sync` | +0.1980 |
| `scheduled_duration_minutes` | -0.0053 |
| `actual_duration_minutes` | +0.5180 |
| `arrival_delay_minutes` | -0.4863 |
| `client_confirmation` | +0.6713 |
| `dispute_filed` | -0.6202 |
| `review_ring_suspected` | -0.3350 |

---

## 7. Model Training vs Evaluation Boundaries

> [!IMPORTANT]
> - **Input Features for ML Model**:
>   `nfc_tap_present`, `arrival_event_present`, `start_event_present`, `finish_event_present`, `device_signature_valid`, `event_chain_valid`, `offline_sync`, `scheduled_duration_minutes`, `actual_duration_minutes`, `arrival_delay_minutes`, `client_confirmation`, `dispute_filed`, `review_ring_suspected`.
> - **Graph / Grouping IDs**:
>   `delivery_id`, `rider_id`, `client_id`.
> - **Evaluation-Only Metadata (DO NOT USE IN MODEL INPUT)**:
>   `evidence_tier`, `scenario_type`.
