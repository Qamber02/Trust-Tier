# %% [markdown]
# # TrustTier (v2): Evidence-Weighted Graph Belief Propagation & Hardware Badge Verification
# **Aligned with Course Project Objectives 2, 3 (5-Cohort Attack Test), and 4 (Graph vs. SQL Benchmark)**

# %%
import os
import glob
import time
import sqlite3
import joblib
import numpy as np
import pandas as pd
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None
from scipy.stats import spearmanr, kendalltau
from sklearn.metrics import (
    roc_auc_score, average_precision_score, f1_score,
    accuracy_score, brier_score_loss
)
from sklearn.ensemble import HistGradientBoostingClassifier

# ==============================================================================
# 1. AUTO-DETECT & LOAD DATASET IN KAGGLE OR LOCAL ENVIRONMENT
# ==============================================================================
def find_dataset(candidates=("trusttier_deliveries.csv", "trusttier_deliveries_2.csv")):
    # Ensure candidates is always treated as a list/tuple of filenames, never iterated char-by-char
    if isinstance(candidates, str):
        candidates = (candidates,)
    for name in candidates:
        if os.path.isfile(name):
            return name
        matches = [p for p in glob.glob(f"/kaggle/input/**/{name}", recursive=True) if os.path.isfile(p)]
        if matches:
            return matches[0]
    any_csv = [p for p in glob.glob("/kaggle/input/**/*.csv", recursive=True) if os.path.isfile(p)]
    if any_csv:
        return any_csv[0]
    local_csv = [p for p in glob.glob("./**/*.csv", recursive=True) if os.path.isfile(p) and "deliveries" in os.path.basename(p)]
    if local_csv:
        return local_csv[0]
    raise FileNotFoundError("Could not locate trusttier_deliveries.csv in local or /kaggle/input/ paths.")

DATA_PATH = find_dataset()
df = pd.read_csv(DATA_PATH)
print(f"Loaded: {DATA_PATH} | Shape: {df.shape}")

# Feature engineering strictly from hardware badge logs & timing (ZERO oracle leakage)
df['duration_ratio'] = df['actual_duration_minutes'] / df['scheduled_duration_minutes'].clip(lower=1)
df['is_ghost_duration'] = (df['duration_ratio'] < 0.25).astype(int)
df['is_severe_delay'] = (df['arrival_delay_minutes'] > 20.0).astype(int)

# 70% Train / 30% Held-Out Test Split
np.random.seed(42)
train_mask = np.random.rand(len(df)) < 0.70
df_train = df[train_mask].copy()
df_test = df[~train_mask].copy()
print(f"Train split: {len(df_train):,} rows | Test split: {len(df_test):,} rows")

# ==============================================================================
# 2. BAYESIAN EVIDENCE-TIER LIKELIHOOD RATIOS: Posterior Odds = Prior Odds * LR(tier)
# ==============================================================================
prior_p = df_train['ground_truth_completed'].mean()
prior_odds = prior_p / (1.0 - prior_p)
log_prior_odds = np.log(prior_odds)

p_tier_pos = df_train[df_train['ground_truth_completed'] == 1]['evidence_tier'].value_counts(normalize=True)
p_tier_neg = df_train[df_train['ground_truth_completed'] == 0]['evidence_tier'].value_counts(normalize=True)
tier_lr_map = (p_tier_pos / p_tier_neg).to_dict()

print("\n--- Empirical Bayesian Likelihood Ratios LR(tier) on Train ---")
for tier in ['self_reported', 'mixed', 'nfc', 'device_signed']:
    lr_val = tier_lr_map[tier]
    print(f"  LR({tier:13s}) = {lr_val:7.4f}  |  log-LR = {np.log(lr_val):+7.4f}")

df['pure_tier_log_lr'] = df['evidence_tier'].map(lambda x: np.log(tier_lr_map[x]))

# ==============================================================================
# 3. STAGE 1: HARDWARE BADGE LOG-LIKELIHOOD MODEL (Cryptographic Flags + Timing)
# ==============================================================================
hardware_features = [
    'nfc_tap_present', 'arrival_event_present', 'start_event_present',
    'finish_event_present', 'device_signature_valid', 'event_chain_valid',
    'offline_sync', 'duration_ratio', 'is_ghost_duration', 'is_severe_delay'
]

tier_dummies_all = pd.get_dummies(df['evidence_tier'], prefix='tier', dtype=float)
X_all_hw = pd.concat([df[hardware_features], tier_dummies_all], axis=1)

hw_model = HistGradientBoostingClassifier(
    max_depth=5, learning_rate=0.05, max_iter=200, random_state=42
)
hw_model.fit(X_all_hw[train_mask], df_train['ground_truth_completed'].values)

eps = 1e-4
p_hw_all = np.clip(hw_model.predict_proba(X_all_hw)[:, 1], eps, 1.0 - eps)
df['hw_log_lr'] = np.log(p_hw_all / (1.0 - p_hw_all)) - log_prior_odds

df_train = df[train_mask].copy()
df_test = df[~train_mask].copy()

# ==============================================================================
# 4. STAGE 2: PARTAW-STYLE ITERATIVE GRAPH BELIEF PROPAGATION (Objective 2 & 3)
# ==============================================================================
def run_trusttier_belief_propagation(data, n_iters=6, decay_alpha=0.85, graph_gamma=1.20):
    """
    Propagates reliability beliefs across Rider <-> Delivery <-> Client bipartite graph.
    Unsupervisedly down-weights collusive client review rings (CLT-2401..2500) when client
    confirmations repeatedly contradict hardware evidence chains and concentrate in bicliques.
    """
    riders = data['rider_id'].unique()
    clients = data['client_id'].unique()
    
    R_rider = pd.Series(prior_p, index=riders)
    W_client = pd.Series(1.0, index=clients)
    
    work_df = data.copy()
    work_df['suspicious_confirm'] = (
        (work_df['client_confirmation'] == 1) &
        ((work_df['event_chain_valid'] == 0) | (work_df['is_ghost_duration'] == 1))
    ).astype(float)
    
    history = []
    for it in range(n_iters):
        work_df['r_prob'] = work_df['rider_id'].map(R_rider)
        work_df['c_weight'] = work_df['client_id'].map(W_client)
        
        # Message A: Rider & Hardware -> Client node credibility
        hw_prob = np.exp(work_df['hw_log_lr']) / (1.0 + np.exp(work_df['hw_log_lr']))
        work_df['client_contradiction'] = work_df['client_confirmation'] * (1.0 - hw_prob)
        
        client_agg = work_df.groupby('client_id').agg(
            mean_r_prob=('r_prob', 'mean'),
            contradiction_rate=('client_contradiction', 'mean'),
            suspicious_conf_rate=('suspicious_confirm', 'mean'),
            unique_riders=('rider_id', 'nunique'),
            total_jobs=('delivery_id', 'count')
        )
        
        rider_concentration = (client_agg['total_jobs'] / client_agg['unique_riders'].clip(lower=1)) / 3.5
        collusion_signal = (
            0.45 * client_agg['contradiction_rate'] +
            0.35 * client_agg['suspicious_conf_rate'] +
            0.20 * (1.0 - client_agg['mean_r_prob']) * np.clip(rider_concentration, 0.0, 2.0)
        )
        W_client = np.clip(1.0 - 1.35 * collusion_signal, 0.02, 1.0)
        
        # Message B: Client & Delivery -> Rider posterior reliability belief
        work_df['c_weight'] = work_df['client_id'].map(W_client)
        work_df['edge_log_lr'] = (
            0.65 * work_df['hw_log_lr'] +
            1.80 * work_df['client_confirmation'] * (work_df['c_weight'] ** 2) -
            1.60 * work_df['dispute_filed'] -
            1.40 * work_df['client_confirmation'] * (1.0 - work_df['c_weight'])
        )
        
        rider_agg = work_df.groupby('rider_id').agg(
            mean_edge_lr=('edge_log_lr', 'mean'),
            mean_c_weight=('c_weight', 'mean')
        )
        
        rider_log_odds = (
            log_prior_odds +
            decay_alpha * rider_agg['mean_edge_lr'] +
            graph_gamma * (rider_agg['mean_c_weight'] - 0.85)
        )
        R_rider = 1.0 / (1.0 + np.exp(-np.clip(rider_log_odds, -10.0, 10.0)))
        
        gt_rider = work_df.groupby('rider_id')['ground_truth_completed'].mean().loc[R_rider.index]
        rho, _ = spearmanr(gt_rider, R_rider)
        history.append((it + 1, rho, W_client.mean()))
        
    return R_rider, W_client, rider_log_odds, history

# Fit BP on Train Split (zero test leakage) and Full Graph (for 200-worker ranking analysis)
R_rider_tr, W_client_tr, _, _ = run_trusttier_belief_propagation(df_train, n_iters=6)
R_rider_all, W_client_all, rider_lo_all, bp_hist = run_trusttier_belief_propagation(df, n_iters=6)

print("\n--- Graph Belief Propagation Convergence ---")
for it, rho, wc in bp_hist:
    print(f"  Iteration {it} | Spearman rho = {rho:.4f} | Mean Client Weight W_c = {wc:.4f}")

# Check Unsupervised Sybil Ring Detection AUC (CLT-2401..2500)
client_eval = pd.DataFrame({
    'client_id': W_client_all.index,
    'W_client': W_client_all.values,
    'is_sybil': (W_client_all.index.str.replace('CLT-', '').astype(int) >= 2401).astype(int)
})
print(f"Unsupervised Sybil Client Ring Detection ROC-AUC: {roc_auc_score(client_eval['is_sybil'], 1.0 - client_eval['W_client']):.6f}")

# ==============================================================================
# 5. STAGE 3: HELD-OUT TEST SET DELIVERY VERIFICATION (n = 29,889 Deliveries)
# ==============================================================================
for split_df in [df_train, df_test]:
    split_df['bp_rider_prob'] = split_df['rider_id'].map(R_rider_tr).fillna(prior_p)
    split_df['bp_client_weight'] = split_df['client_id'].map(W_client_tr).fillna(1.0)
    split_df['bp_edge_log_lr'] = (
        0.65 * split_df['hw_log_lr'] +
        1.80 * split_df['client_confirmation'] * (split_df['bp_client_weight'] ** 2) -
        1.60 * split_df['dispute_filed'] -
        1.40 * split_df['client_confirmation'] * (1.0 - split_df['bp_client_weight'])
    )

graph_features = hardware_features + [
    'client_confirmation', 'dispute_filed',
    'pure_tier_log_lr', 'hw_log_lr',
    'bp_rider_prob', 'bp_client_weight', 'bp_edge_log_lr'
]

X_tr_full = pd.concat([df_train[graph_features], pd.get_dummies(df_train['evidence_tier'], prefix='tier', dtype=float)], axis=1)
X_te_full = pd.concat([df_test[graph_features], pd.get_dummies(df_test['evidence_tier'], prefix='tier', dtype=float)], axis=1)
y_test = df_test['ground_truth_completed'].values

trusttier_clf = HistGradientBoostingClassifier(
    max_depth=6, learning_rate=0.05, max_iter=250, random_state=42
)
trusttier_clf.fit(X_tr_full, df_train['ground_truth_completed'].values)

p_test_naive = df_test['finish_event_present'].values
p_test_flat = df_test['client_confirmation'].values
p_test_tier = 1.0 / (1.0 + np.exp(-(log_prior_odds + df_test['pure_tier_log_lr'].values)))
p_test_hw = p_hw_all[~train_mask]
p_test_full = trusttier_clf.predict_proba(X_te_full)[:, 1]

print(f"\n--- Held-Out Test Set Delivery Verification Benchmark (n = {len(df_test):,}) ---")
for name, preds in [
    ('1. Naive Self-Reported (finish_event)', p_test_naive),
    ('2. Flat Client Confirmation Rating', p_test_flat),
    ('3. Pure Bayesian Evidence-Tier (LR only)', p_test_tier),
    ('4. Hardware Badge ML (No Graph)', p_test_hw),
    ('5. TrustTier Graph BP + Hardware (Full)', p_test_full)
]:
    print(
        f"{name:40s} | ROC-AUC={roc_auc_score(y_test, preds):.4f} "
        f"| PR-AUC={average_precision_score(y_test, preds):.4f} "
        f"| F1={f1_score(y_test, (preds >= 0.5).astype(int)):.4f} "
        f"| Acc={accuracy_score(y_test, (preds >= 0.5).astype(int))*100:5.2f}% "
        f"| Brier={brier_score_loss(y_test, preds):.4f}"
    )

# ==============================================================================
# 6. OBJECTIVE 3: 5-COHORT RIDER RANKING & ATTACK RESISTANCE BENCHMARK
# ==============================================================================
rider_eval = df.groupby('rider_id').agg(
    gt_rate=('ground_truth_completed', 'mean'),
    naive_self_claim=('finish_event_present', 'mean'),
    flat_client_rating=('client_confirmation', 'mean'),
    pure_tier_log_lr=('pure_tier_log_lr', 'mean')
)
rider_eval['pure_tier_prob'] = 1.0 / (1.0 + np.exp(-(log_prior_odds + rider_eval['pure_tier_log_lr'])))
rider_eval['trusttier_bp_prob'] = R_rider_all.loc[rider_eval.index]
rider_eval['trusttier_bp_log_odds'] = rider_lo_all.loc[rider_eval.index]
rider_eval['rider_num'] = rider_eval.index.str.replace('RDR-', '').astype(int)

def get_5_cohorts(r):
    if r <= 130: return '1. Honest Online (RDR 001-130)'
    elif r <= 160: return '2. Honest Offline (RDR 131-160)'
    elif r <= 180: return '3. Glitched Badge (RDR 161-180)'
    elif r <= 190: return '4. Collusive Review Ring (RDR 181-190)'
    else: return '5. Ghost/Tampered Attackers (RDR 191-200)'

rider_eval['cohort'] = rider_eval['rider_num'].apply(get_5_cohorts)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
print("\n--- 5-Cohort Mean Reliability Scores ---")
print(rider_eval.groupby('cohort')[['gt_rate', 'flat_client_rating', 'pure_tier_prob', 'trusttier_bp_prob']].mean().round(4))

actual_attackers = set(rider_eval[rider_eval['rider_num'] >= 181].index)
ring_attackers = set(rider_eval[(rider_eval['rider_num'] >= 181) & (rider_eval['rider_num'] <= 190)].index)
glitched_honest = set(rider_eval[(rider_eval['rider_num'] >= 161) & (rider_eval['rider_num'] <= 180)].index)

print("\n--- Objective 3: Worker Ranking & Review-Ring Resistance (200 Workers) ---")
for name, col in [
    ('1. Naive Self-Reported Claim', 'naive_self_claim'),
    ('2. Flat Client Confirmation', 'flat_client_rating'),
    ('3. Pure Tier Log-LR (No Graph)', 'pure_tier_log_lr'),
    ('4. TrustTier Graph BP (Full)', 'trusttier_bp_log_odds')
]:
    rho, _ = spearmanr(rider_eval['gt_rate'], rider_eval[col])
    tau, _ = kendalltau(rider_eval['gt_rate'], rider_eval[col])
    bottom20 = set(rider_eval.nsmallest(20, col).index)
    top10 = set(rider_eval.nlargest(10, col).index)
    recall_all20 = len(bottom20 & actual_attackers) / 20.0
    ring_caught = len(bottom20 & ring_attackers) / 10.0
    ring_in_top10 = len(top10 & ring_attackers) / 10.0
    fpr_glitch = len(bottom20 & glitched_honest) / 20.0
    print(
        f"{name:32s} | Spearman={rho:.4f} | Kendall={tau:.4f} "
        f"| Attacker Recall@20={recall_all20*100:5.1f}% | Ring Caught@20={ring_caught*100:5.1f}% "
        f"| Ring Fooled into Top-10={ring_in_top10*100:5.1f}% | Glitched FPR@20={fpr_glitch*100:5.1f}%"
    )

# ==============================================================================
# 7. OBJECTIVE 4: RELATIONAL SQL JOINS VS. GRAPH TRAVERSAL LATENCY BENCHMARK
# ==============================================================================
print("\n--- Objective 4: 2-Hop Trust Lookup Benchmark (SQL Join vs. Graph Traversal) ---")
for n_rows in [10000, 50000, 100000]:
    sub_df = df.iloc[:n_rows].copy()
    sample_riders = sub_df['rider_id'].unique()[:50]
    
    conn = sqlite3.connect(':memory:')
    sub_df[['delivery_id', 'rider_id', 'client_id', 'client_confirmation', 'event_chain_valid']].to_sql('deliveries', conn, index=False)
    cur = conn.cursor()
    cur.execute("CREATE INDEX idx_r ON deliveries(rider_id);")
    cur.execute("CREATE INDEX idx_c ON deliveries(client_id);")
    conn.commit()
    
    t0 = time.perf_counter()
    for r_id in sample_riders:
        cur.execute("""
            SELECT d2.rider_id, COUNT(*), AVG(d2.client_confirmation), AVG(d2.event_chain_valid)
            FROM deliveries d1
            JOIN deliveries d2 ON d1.client_id = d2.client_id
            WHERE d1.rider_id = ? AND d2.rider_id != ?
            GROUP BY d2.rider_id
        """, (r_id, r_id))
        _ = cur.fetchall()
    sql_ms = ((time.perf_counter() - t0) / len(sample_riders)) * 1000.0
    conn.close()
    
    r_to_c = sub_df.groupby('rider_id')['client_id'].unique().to_dict()
    c_to_r = sub_df.groupby('client_id')['rider_id'].unique().to_dict()
    r_stats = sub_df.groupby('rider_id')[['client_confirmation', 'event_chain_valid']].mean().to_dict('index')
    
    t0 = time.perf_counter()
    for r_id in sample_riders:
        co_riders = {
            nbr_r: r_stats[nbr_r]
            for c_id in r_to_c.get(r_id, [])
            for nbr_r in c_to_r.get(c_id, [])
            if nbr_r != r_id
        }
    graph_ms = ((time.perf_counter() - t0) / len(sample_riders)) * 1000.0
    print(f"  {n_rows:7,d} events | SQL 2-Hop Join: {sql_ms:6.2f} ms | Graph 2-Hop Traversal: {graph_ms:5.2f} ms | Speedup: {sql_ms/max(graph_ms, 1e-6):5.1f}x")

# ==============================================================================
# 8. EXPORT TRAINED MODELS & GRAPH SCORES
# ==============================================================================
rider_eval.to_csv("trusttier_v2_rider_scores.csv")
W_client_all.rename("credibility_weight").to_csv("trusttier_v2_client_weights.csv")
joblib.dump({"hw_model": hw_model, "trusttier_clf": trusttier_clf, "tier_lr_map": tier_lr_map}, "trusttier_v2_models.joblib")
print("\nSaved: trusttier_v2_rider_scores.csv, trusttier_v2_client_weights.csv, trusttier_v2_models.joblib")
