"""Generate a scalable synthetic worker/event stream (10k through 1M rows)."""
import argparse
import csv
import random
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="trusttier_live_events.csv")
    args = parser.parse_args()
    if not 1 <= args.events <= 1_000_000:
        parser.error("--events must be between 1 and 1,000,000")
    rng = random.Random(args.seed)
    with open(args.output, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["event_id", "worker_id", "client_id", "type", "tier", "ground_truth", "client_confirmation", "scenario", "device_ts"])
        for i in range(args.events):
            worker_no = rng.randint(1, 200)
            cohort = "review_ring" if 181 <= worker_no <= 190 else "ghost" if worker_no >= 191 else "honest"
            scenario = rng.choices(["honest", "late", "fake_checkin", "review_ring"], [0.72, 0.12, 0.08, 0.08])[0]
            if cohort in ("ghost", "review_ring"):
                scenario = "review_ring" if cohort == "review_ring" else "fake_checkin"
            truth = int(rng.random() < ({"honest": .98, "late": .84, "fake_checkin": .03, "review_ring": .06}[scenario]))
            tier = "signed" if scenario in ("honest", "late") and rng.random() < .72 else "nfc" if scenario == "fake_checkin" or rng.random() < .5 else "self"
            confirm = int(scenario == "review_ring" or (truth and rng.random() < .9))
            writer.writerow([f"EVT-{i+1:07}", f"RDR-{worker_no:03}", f"CLT-{rng.randint(1,2500):04}", rng.choice(["arrive","start","finish"]), tier, truth, confirm, scenario, datetime.now(timezone.utc).isoformat()])
    print(f"Generated {args.events:,} synthetic rows in {args.output}")


if __name__ == "__main__": main()
