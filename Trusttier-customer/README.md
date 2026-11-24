# TrustTier Customer App

The customer side of TrustTier. The customer finds workers, requests jobs,
follows a job timeline with proof types, then confirms and rates the work.

## Run

1. Open a terminal in this folder.
2. Get packages: flutter pub get
3. Run: flutter run

## Screens

- Workers: search, trade filters, trust score rings, Add worker button
- Worker profile: score breakdown, recent activity, reviews, Request this worker
- My jobs: job timeline, Cancel request, Confirm and rate, Report a problem

## How the score works

Each event multiplies the worker's odds by a weight for its proof type:
self-report 1.1, NFC tap 1.3, device-signed 1.8.
The ring length is the score. The ring colours show the mix of evidence.
The weights are in TierInfo.lr in lib/main.dart.

## Add worker

Tap Add worker on the Workers screen to add a rider or other worker.
Added workers are saved on the phone. Remove them from their profile.

## Using it with the real project

All other data is fake and lives in the Store class in lib/main.dart.
The demo buttons on the job page simulate badge events. Replace Store with
calls to your FastAPI service, and remove the demo buttons later.