"""Benchmark indexed relational 2-hop lookups against recursive-CTE traversal."""
import argparse
import csv
import math
import sqlite3
import time

import pandas as pd
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, default=[10_000, 100_000, 1_000_000])
    parser.add_argument("--seed-csv", default="trusttier_deliveries.csv")
    parser.add_argument("--output", default="graph_benchmark.csv")
    parser.add_argument("--chart", default="graph_benchmark.png")
    args = parser.parse_args()
    events = pd.read_csv(args.seed_csv, usecols=["delivery_id", "rider_id", "client_id"]).drop_duplicates("delivery_id")
    results = []
    for size in args.sizes:
        copies = math.ceil(size / len(events))
        frame = pd.concat([events] * copies, ignore_index=True).iloc[:size]
        db = sqlite3.connect(":memory:")
        frame.to_sql("events", db, index=False)
        db.execute("create index ev_worker on events(rider_id)")
        db.execute("create index ev_client on events(client_id)")
        db.execute("create table edges(src text,dst text,kind text)")
        db.execute("insert into edges select rider_id,client_id,'worker-client' from events")
        db.execute("insert into edges select client_id,rider_id,'client-worker' from events")
        db.execute("create index edge_src on edges(src,kind)")
        sample = frame.rider_id.iloc[0]
        start = time.perf_counter(); db.execute("select distinct e2.rider_id from events e1 join events e2 on e1.client_id=e2.client_id where e1.rider_id=? and e2.rider_id<>?", (sample,sample)).fetchall(); join_ms=(time.perf_counter()-start)*1000
        start = time.perf_counter(); db.execute("with recursive n(id,depth) as (select ?,0 union select e.dst,n.depth+1 from edges e join n on e.src=n.id where n.depth<2) select distinct id from n", (sample,)).fetchall(); cte_ms=(time.perf_counter()-start)*1000
        results.append({"events":size,"loaded_rows":len(frame),"relational_join_ms":round(join_ms,4),"recursive_cte_ms":round(cte_ms,4),"speedup":round(join_ms/max(cte_ms,1e-9),3)})
        db.close()
    with open(args.output,"w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=results[0].keys());writer.writeheader();writer.writerows(results)
    df=pd.DataFrame(results); ax=df.plot(x="events",y=["relational_join_ms","recursive_cte_ms"],marker="o",logx=True,logy=True,title="TrustTier Graph Lookup Benchmark");ax.set_ylabel("milliseconds");ax.figure.tight_layout();ax.figure.savefig(args.chart,dpi=160)
    print(df.to_string(index=False)); print(f"Wrote {args.output} and {args.chart}")


if __name__ == "__main__": main()
