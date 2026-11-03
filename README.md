# TrustTier: Evidence-Weighted Belief Propagation for Offline Gig Worker Reliability

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An advanced decentralized and cryptographic framework that predicts whether a gig delivery was genuinely completed in connectivity-constrained environments (such as Gwadar port and peri-urban hubs), using **ESP32 signed hardware badges**, **NFC check-ins**, **Bayesian evidence tiers**, and **bipartite graph belief propagation**.

---

## 🚀 Key Highlights & Research Contributions

1. **Deterministic Bayesian Evidence Tiers**:
   Deliveries are categorized into four objective physical tiers satisfying strict monotonic likelihood ordering ($LR(\text{self}) < LR(\text{mixed}) < 1.0 < LR(\text{nfc}) < LR(\text{signed})$):
   * `device_signed` ($LR = 48.95$): Full ESP32 digital signature + unbroken sequential SHA-256 event hash chain.
   * `nfc` ($LR = 1.88$): Physical NFC door tag tapped on client site.
   * `mixed` ($LR = 0.25$): Broken event chain or partial hardware telemetry.
   * `self_reported` ($LR = 0.09$): App-only button claim with no physical cryptographic proof.

2. **Unsupervised Sybil Review Ring Defense**:
   Bipartite belief propagation over Worker $\leftrightarrow$ Customer delivery graphs downweights collusive client rings ($CLT\text{-}2401..2500$) from $W_c = 1.0$ to $W_c = 0.02$, dropping collusion belief from $95.5\%$ (naive rating) to **$3.3\%$** ($100\%$ precision).

3. **Offline Flash Resilience**:
   ESP32 hardware badge securely logs and signs events to SPIFFS flash memory during cellular blackouts, syncing without penalty upon reconnection.

4. **10.0x Real-Time Graph Traversal**:
   Achieves sub-3ms 2-hop graph neighborhood evaluation ($2.55\text{ ms}$ at 100k events vs $25.40\text{ ms}$ for relational SQL joins).

---

## 📁 Repository Structure

```text
├── trusttier_deliveries.csv          # 100,000 synthetic delivery records (Seed 42)
├── generate_dataset.py               # Reproducible generator for 200 riders & 2,500 clients
├── verify_dataset.py                 # 10-point automated mathematical validation suite
├── trusttier_kaggle_pipeline.py      # End-to-end training & graph belief propagation pipeline
├── ui_server.py                      # FastAPI real-time inference server (Port 8000)
├── test_ui.py                        # Automated API testing client
├── simple_test_ui.html               # Standalone manual test sandbox (Double-clickable)
├── static/
│   ├── index.html                    # Glassmorphism full analytics dashboard
│   └── simple.html                   # Interactive manual scenario tester
├── trusttier_v2_models.joblib        # Trained scikit-learn models (107 & 141 Boosted Trees)
├── trusttier_v2_rider_scores.csv     # 200-Rider belief scores and cohort rankings
├── trusttier_v2_client_weights.csv   # 2,500 Client credibility weights
├── DATA_DICTIONARY.md                # Full field reference, data types, and leakage guidelines
├── DATASET_GENERATION_REPORT.md      # Statistical validation and cohort distribution report
└── TrustTier_Project_Proposal.docx   # Academic project proposal document
```

---

## 📊 Benchmark Results (Held-Out Test Set, $n = 29,889$)

| Method | ROC-AUC | PR-AUC | F1-Score | Accuracy | Brier Score | Attacker Recall |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1. Naive Self-Reported Claim | 0.7192 | 0.7487 | 0.8305 | 76.74% | 0.2326 | 0.0% |
| 2. Flat Client Confirmation | 0.8314 | 0.8393 | 0.8786 | 84.63% | 0.1537 | 50.0% |
| 3. Pure Bayesian Tier ($LR$) | 0.9214 | 0.9386 | 0.8926 | 87.07% | 0.0996 | 100.0% |
| 4. Hardware Badge ML (No Graph) | 0.9825 | 0.9880 | 0.9621 | 95.31% | 0.0379 | 100.0% |
| **5. TrustTier Graph BP + Hardware** | **0.9865** | **0.9902** | **0.9823** | **97.80%** | **0.0205** | **100.0%** |

---

## 🛠️ Quickstart Guide

### 1. Installation
Clone the repository and install requirements:
```bash
git clone https://github.com/Qamber02/Trust-Tier.git
cd Trust-Tier
pip install fastapi uvicorn pandas numpy scikit-learn joblib
```

### 2. Verify Dataset Integrity
Run the automated verification test suite:
```bash
python verify_dataset.py
```

### 3. Launch the Interactive Testing Suite
Start the FastAPI server:
```bash
python ui_server.py
```
Open your browser:
* **Interactive Manual Test Sandbox**: [http://127.0.0.1:8000/simple](http://127.0.0.1:8000/simple)
* **Comprehensive Analytics Dashboard**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
* **Or double-click `simple_test_ui.html`** to test locally in any browser!

---

## 📄 License
MIT License. Built for course research on Advanced Distributed and Mobile Systems (ADMS).
