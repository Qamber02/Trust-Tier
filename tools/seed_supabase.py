"""Load the existing reproducible CSV artifacts into a configured Supabase project."""
import argparse
import os

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
    # Keep data seeding bounded and repeatable. The operational path is /sync;
    # generated historical rows are marked unverified rather than fabricated as signed events.
    print("Seeded worker, client and score records. Historical synthetic events remain in the CSV; use live signed events through /sync.")


if __name__ == "__main__": main()
