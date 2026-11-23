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

## Connected demo (FastAPI, Supabase, dashboard, apps, badge)

The original model dashboard remains available at `/legacy`. The root URL now serves the live operations dashboard (`static/live.html`), which subscribes to Supabase Realtime when configured and otherwise refreshes the local API demo every two seconds.

1. Install Python dependencies: `python -m pip install -r requirements.txt`.
2. Copy `.env.example` to `.env`; configure Supabase URL, anon key and **server-only** service role key. Apply both migrations in `supabase/migrations/` in order via the Supabase SQL editor. Enable Supabase Anonymous Sign-Ins for read-only score Realtime in the demo clients. Never put the service role key in a Flutter app or browser.
3. Start the API: `uvicorn ui_server:app --host 0.0.0.0 --port 8000`. Seed workers and clients with `python tools/seed_supabase.py` (requires Supabase credentials).
4. Test live sync locally: `python tools/provision_badge.py --device DEMO-ESP32-001 --worker RDR-025`, then `python tools/badge_simulator.py --offline --tampered`. The simulator keeps its private key in an ignored local file.
5. Generate up to one million synthetic rows with `python tools/generate_live_data.py --events 1000000`; run the graph benchmark with `python tools/benchmark_graph.py` (SQLite emulates indexed relational and recursive traversal; it is not a hosted Supabase latency claim).
6. For each Flutter project: `flutter pub get`, then `flutter run --dart-define=TRUSTTIER_API_URL=http://10.0.2.2:8000 --dart-define=SUPABASE_URL=... --dart-define=SUPABASE_ANON_KEY=...`. Use your host LAN IP on physical phones. Service role credentials are never passed to Flutter.
7. Firmware is under `firmware/`. Use Arduino IDE with ESP32 core 3.3.12 and the MFRC522 (GithubCommunity), Rtc (Makuna), ThreeWire, ArduinoJson, and Crypto libraries. Copy `firmware/include/secrets.example.h` to `firmware/include/secrets.h`; provision a device key before flashing. All GPIO constants live in `firmware/include/pins.h`.

#### Fixed badge wiring — ESP32-WROOM-32 DevKit (30-pin, HW-463)

On this board the printed D label is the GPIO number. RC522 `SDA` is its SPI `SS/CS` pin. The firmware calls `SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, PIN_SS)` and uses only the constants in `pins.h`; no I²C devices or USB-serial GPIOs are used.

```text
RC522 RFID (SPI)             DS1302 RTC (3-wire; no I²C)
SDA / SS / CS → GPIO 5       CLK → GPIO 27
SCK           → GPIO 18      DAT → GPIO 26
MOSI          → GPIO 23      RST → GPIO 25
MISO          → GPIO 19      VCC → 3V3
RST           → GPIO 22      GND → GND
3.3V → 3V3
GND  → GND
IRQ  → not connected
```

The simulator provides the currently testable signed-event and offline-batch workflow; firmware still requires compilation and physical-board validation.

### Integration status and limitations

The FastAPI ingestion verifies Ed25519 signatures and SHA-256 event chaining, rejects duplicates, updates Bayesian tier scores, and writes to Supabase when configured. Rejected events are retained by the local demo API. The live browser dashboard uses the public anon key only. Flutter apps retain their existing mock Store for offline fallback; `TrustTierService` exposes API actions and Supabase listeners. Customer and rider trust-score views now subscribe to Supabase Realtime when configured. Apply database migrations before running the live path. Firmware has not been compiled or tested on physical hardware; validate it with the specified board and modules before field use.
