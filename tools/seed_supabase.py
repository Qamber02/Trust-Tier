"""Load the existing reproducible CSV artifacts into a configured Supabase project."""
import argparse
import os
import uuid

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client


def upload(client, table, rows, chunk_size=500):
    for start in range(0, len(rows), chunk_size):
        client.table(table).upsert(rows[start:start + chunk_size]).execute()
        print(f"{table}: {min(start + chunk_size, len(rows))}/{len(rows)}")


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="trusttier_deliveries.csv")
    args = parser.parse_args()
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env")
    client = create_client(url, key)
    deliveries = pd.read_csv(args.csv)
    rider_ids = sorted(deliveries.rider_id.unique())
    client_ids = sorted(deliveries.client_id.unique())
    upload(client, "workers", [{"id": x, "display_name": x, "cohort": "simulated"} for x in rider_ids])
    upload(client, "clients", [{"id": x, "display_name": x} for x in client_ids])
    scores = pd.read_csv("trusttier_v2_rider_scores.csv") if os.path.exists("trusttier_v2_rider_scores.csv") else None
    if scores is not None:
        upload(client, "trust_scores", [{"worker_id": r.rider_id, "score": float(r.trusttier_bp_prob)} for r in scores.itertuples()])
    upload(client, "devices", [{"id": f"SEED-{worker}", "worker_id": worker,
                                 "public_key": "synthetic-unprovisioned", "algorithm": "ed25519"}
                                for worker in rider_ids])

    tier_map = {"device_signed": "signed", "nfc": "nfc", "self_reported": "self", "mixed": "self"}
    jobs = []
    events = []
    reviews = []
    disputes = []
    payments = []
    for row in deliveries.itertuples(index=False):
        job_id = row.delivery_id
        jobs.append({"id": job_id, "worker_id": row.rider_id, "client_id": row.client_id,
                     "title": f"Synthetic delivery {job_id}", "status": "completed" if row.ground_truth_completed else "disputed"})
        events.append({"id": f"{job_id}-seed", "device_id": f"SEED-{row.rider_id}",
                       "worker_id": row.rider_id, "job_id": job_id, "client_id": row.client_id,
                       "type": "finish", "evidence_tier": tier_map[row.evidence_tier],
                       "device_ts": "2024-01-01T00:00:00Z", "payload": {"synthetic": True},
                       "signature": "not-signed-synthetic-history", "prev_hash": "",
                       "hash": f"synthetic-{job_id}", "verified": False,
                       "rejection_reason": "synthetic historical record; not cryptographically verified"})
        if len(reviews) < 2000 and row.ground_truth_completed:
            stars = 5 if row.client_confirmation else 3
            text = "Reliable delivery, thank you." if stars == 5 else "Delivery completed with some delay."
            reviews.append({"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"review:{job_id}")),
                            "job_id": job_id, "worker_id": row.rider_id, "client_id": row.client_id,
                            "stars": stars, "body": text, "sentiment": 0.8 if stars == 5 else 0.1})
        if len(disputes) < 2000 and row.dispute_filed:
            disputes.append({"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"dispute:{job_id}")),
                             "job_id": job_id, "worker_id": row.rider_id, "client_id": row.client_id,
                             "reason": "Synthetic dispute: package reported missing.", "status": "open"})
        if len(payments) < 2000 and row.ground_truth_completed:
            payments.append({"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"payment:{job_id}")),
                             "job_id": job_id, "worker_id": row.rider_id, "amount": 300,
                             "currency": "PKR", "status": "released"})

    upload(client, "jobs", jobs)
    upload(client, "events", events)
    upload(client, "reviews", reviews)
    upload(client, "disputes", disputes)
    upload(client, "payments", payments)
    print("Synthetic event rows are deliberately marked unverified; only POST /sync establishes cryptographic verification.")


if __name__ == "__main__": main()
