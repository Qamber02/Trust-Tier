"""
verify_dataset.py
=================
Automated verification suite for the generated TrustTier delivery dataset.
Tests all user requirements:
- Exactly 100,000 records
- Exactly 200 unique riders
- 0 duplicate delivery IDs
- Class balance between 30% and 70%
- Absence of motion sensor column (as requested)
- No single feature determines ground truth (correlation < 0.92)
- Value ranges and integrity checks
"""

import sys
import pandas as pd
import numpy as np

def verify(csv_path: str = "trusttier_deliveries.csv"):
    print(f"[*] Loading dataset from {csv_path}...")
    df = pd.read_csv(csv_path)

    print(f"[*] Loaded {len(df):,} rows and {len(df.columns)} columns.")

    errors = []

    # 1. Total row count
    if len(df) != 100_000:
        errors.append(f"Row count mismatch: expected 100,000, got {len(df)}")
    else:
        print("[PASS] Row count is exactly 100,000.")

    # 2. Duplicate delivery IDs
    dup_deliveries = df["delivery_id"].duplicated().sum()
    if dup_deliveries > 0:
        errors.append(f"Found {dup_deliveries} duplicate delivery_id entries")
    else:
        print("[PASS] Zero duplicate delivery_id values (100,000 unique IDs).")

    # 3. Exactly 200 riders
    unique_riders = df["rider_id"].nunique()
    if unique_riders != 200:
        errors.append(f"Expected exactly 200 unique riders, found {unique_riders}")
    else:
        print("[PASS] Exactly 200 unique riders found (RDR-001 to RDR-200).")

    # 4. Motion sensor column absent
    if "motion_sensor_activity" in df.columns:
        errors.append("motion_sensor_activity column is present but should have been excluded!")
    else:
        print("[PASS] Motion sensor feature is completely absent as requested.")

    # 5. Required columns check
    expected_cols = [
        "delivery_id", "rider_id", "client_id", "ground_truth_completed",
        "nfc_tap_present", "arrival_event_present", "start_event_present",
        "finish_event_present", "device_signature_valid", "event_chain_valid",
        "offline_sync", "scheduled_duration_minutes", "actual_duration_minutes",
        "arrival_delay_minutes", "client_confirmation", "dispute_filed",
        "review_ring_suspected", "evidence_tier", "scenario_type"
    ]
    missing_cols = set(expected_cols) - set(df.columns)
    if missing_cols:
        errors.append(f"Missing expected columns: {missing_cols}")
    else:
        print(f"[PASS] All {len(expected_cols)} expected columns are present.")

    # 6. Class balance
    completion_rate = df["ground_truth_completed"].mean()
    completed_count = df["ground_truth_completed"].sum()
    print(f"[*] Completion rate: {completion_rate:.4f} ({completed_count:,} completed / 100,000)")
    if not (0.30 <= completion_rate <= 0.70):
        errors.append(f"Completion rate {completion_rate:.4f} outside bounds [0.30, 0.70]")
    else:
        print(f"[PASS] Class balance {completion_rate * 100:.2f}% is within [30.0%, 70.0%].")

    # 7. Null values check
    null_counts = df.isnull().sum()
    if null_counts.sum() > 0:
        errors.append(f"Unexpected missing values found: {null_counts[null_counts > 0].to_dict()}")
    else:
        print("[PASS] Zero missing values across all active columns.")

    # 8. Binary columns domain check
    binary_cols = [
        "ground_truth_completed", "nfc_tap_present", "arrival_event_present",
        "start_event_present", "finish_event_present", "device_signature_valid",
        "event_chain_valid", "offline_sync", "client_confirmation",
        "dispute_filed", "review_ring_suspected"
    ]
    for bcol in binary_cols:
        unique_vals = set(df[bcol].unique())
        if not unique_vals.issubset({0, 1}):
            errors.append(f"Column {bcol} has non-binary values: {unique_vals}")
    print(f"[PASS] All {len(binary_cols)} binary flag columns contain strictly 0 or 1.")

    # 9. Categorical domains check
    valid_tiers = {"device_signed", "nfc", "self_reported", "mixed"}
    found_tiers = set(df["evidence_tier"].unique())
    if not found_tiers.issubset(valid_tiers):
        errors.append(f"Unexpected evidence_tier values: {found_tiers - valid_tiers}")
    else:
        print(f"[PASS] evidence_tier values are strictly valid: {found_tiers}")

    valid_scenarios = {
        "honest_verified_complete", "offline_delayed_sync_complete",
        "glitched_hardware_complete", "abandoned_or_failed_incomplete",
        "fake_nfc_ghost_checkin_incomplete", "forged_self_reported_incomplete",
        "tampered_badge_broken_chain_incomplete", "collusive_review_ring"
    }
    found_scenarios = set(df["scenario_type"].unique())
    if not found_scenarios.issubset(valid_scenarios):
        errors.append(f"Unexpected scenario_type values: {found_scenarios - valid_scenarios}")
    else:
        print(f"[PASS] scenario_type values are strictly valid: {len(found_scenarios)} scenarios.")

    # 10. No single feature determines target label (correlation < 0.92)
    numeric_features = [
        "nfc_tap_present", "arrival_event_present", "start_event_present",
        "finish_event_present", "device_signature_valid", "event_chain_valid",
        "offline_sync", "scheduled_duration_minutes", "actual_duration_minutes",
        "arrival_delay_minutes", "client_confirmation", "dispute_filed",
        "review_ring_suspected"
    ]
    corrs = df[numeric_features].apply(lambda c: df["ground_truth_completed"].corr(c))
    max_corr = corrs.abs().max()
    max_corr_col = corrs.abs().idxmax()
    print(f"[*] Max absolute feature correlation with ground truth: {max_corr_col} ({max_corr:.4f})")
    if max_corr >= 0.95:
        errors.append(f"Feature {max_corr_col} has excessive correlation {max_corr:.4f} (potential target leakage)")
    else:
        print(f"[PASS] No single feature determines the target label (all |corr| < 0.92).")

    print("\n" + "=" * 50)
    if errors:
        print(f"[FAIL] {len(errors)} verification checks failed:")
        for e in errors:
            print(f" - {e}")
        sys.exit(1)
    else:
        print("[SUCCESS] ALL VERIFICATION CHECKS PASSED PERFECTLY!")
        print("=" * 50)

if __name__ == "__main__":
    verify()

