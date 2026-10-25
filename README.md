# SecondLook

SecondLook helps a coach review a player's submitted footage by playing only the moments with evidence, recording an accept, reject or correction on each one, and keeping a summary that says what the footage shows and what it does not. It produces no ratings or odds.

Built solo at Cal Hacks 13.0. The coach need is a hypothesis; no coach has used it yet.

## What it does

- **Coach review** (`/review/<submission>`): a moments list from Claude's observations, each tied to exact frame times. "Watch moments" plays every evidence interval in order with 1.5 s of context, merging overlaps; "Watch accepted only" plays the accepted ones. Accept, reject with a reason, undo, or correct the player. A coach note and a next-footage request are saved. The summary groups accepted moments by category, lists pending ones, and lists what the footage does not establish. Every open session updates live.
- **Scout** (`/scout`): choose a file, confirm the rights, then the video. Pause, click one player or drag one box, enter a name, and press Analyse player. The review is the video, one row of filters, a brief labelled "AI-generated, awaiting review" with at most three findings, and a short count of actions. Unclear outcomes stay separate. A lost track shows one frame. Diagnostics stay collapsed. Rejecting an event removes it from the brief. This describes the analysed footage, not a career.
- **Prepare** (`/prepare/<submission>/<window>`): box the player on sampled frames, optionally ask the tracker for estimates (they stay labelled estimated until confirmed), save a selection and queue analysis. A correction saves a new selection; moments made for the old one become stale in every session, leave the playlist and summary, and stay in history.
- **Honest effort and cost**: the review shows hand-drawn boxes, confirmed estimates and saved corrections apart from automatic sampling, tracker proposals and model time. Each window shows its live calls, cached reuses, failed jobs and attempts whose usage the provider did not report.

## How it works

```text
coach review page --live queries, mutations--> Convex: submissions, windows, selections (append-only),
                                                analysis queue, runs and observations (immutable),
                                                decisions, notes, footage requests (append-only)
prepare page --frames, tracker proposals--> FastAPI --> local MP4 and frames, SQLite jobs, budget, cache
Python worker --claim, progress, publish (worker secret)--> Convex
              --short windows: one Claude vision call per window and selection--> Anthropic
              --scout: local YOLO26n + BoT-SORT, then Claude only for candidate moments--> Anthropic
```

Convex owns all review state. SQLite owns media, frames, execution jobs, the budget ledger and the result cache. No field has two owners. The Python worker connects out to Convex, so no hosted function needs to reach the laptop.

## Run locally

Requirements: Python 3.12, Node 20+, FFmpeg on PATH, an Anthropic key. From `secondlook/`:

```powershell
python -m venv services\api\.venv
services\api\.venv\Scripts\python -m pip install -r services\api\requirements.lock
copy .env.example .env        # then put ANTHROPIC_API_KEY in .env; never commit it
cd apps\web; npm install; cd ..\..
```

Three terminals:

```powershell
# 1. Convex (first run provisions a deployment and writes apps/web/.env.local)
cd apps\web; npx convex dev

# 2. Worker connection, once per deployment, then the API (it runs the worker bridge)
services\api\.venv\Scripts\python scripts\convex_setup.py
services\api\.venv\Scripts\python -m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8000

# 3. Web
cd apps\web; npm run dev
```

`convex_setup.py` creates a worker secret in `.env` and sets the same value as `WORKER_SECRET` on the deployment through a temporary file. It never prints it.

Demo data: upload clips in the single-clip workbench at http://localhost:3000/workbench, mark the player, then list their video and manifest ids in `scripts/review_seed.json` and run `services\api\.venv\Scripts\python scripts\seed_review.py`. It prints one review link per submission. The ids in the committed file belong to the builder's machine.

Open the printed link. The code in it is stored in that browser and removed from the address bar. `/review` lists the submissions the browser holds a code for.

## Checks

```powershell
cd services\api; .\.venv\Scripts\python -m pytest
cd ..\..\apps\web; npm test; npx tsc --noEmit
cd ..\..; services\api\.venv\Scripts\python scripts\check_convex.py   # API stopped; acts as the worker
```

`check_convex.py` runs 15 rule checks against the live deployment: the short-clip review rules, plus a scout claim, cancel, a finding from two events, and that rejecting those events clears the finding.

## Convex (Best Use of Convex)

What the build uses, all exercised in the demo:

- **Schema and indexes** (`apps/web/convex/schema.ts`): submissions, windows, revisions, the analysis queue, runs, observations, decisions, notes, footage requests, and correction requests. Scout runs stream events through `openRun`, `addObservations` and `closeRun`. The brief is computed in `convex/lib/scoutBrief.ts` from the current events, with no model call.
- **Live queries** (`review.get`, `review.inbox`) through `useQuery`. Two browser sessions see each other's decisions, notes, footage requests, queue progress and corrections without a refresh.
- **Transactional mutations** (`review.ts`) enforce the review rules:
  - Decisions on stale or held moments are refused.
  - A selection saved on top of a newer one is refused (`revision_conflict`).
  - An estimated box cannot be saved as manual without "Confirm box".
  - Queueing is deduplicated.
- **Worker functions** (`worker.ts`) are gated by a secret stored as a Convex environment variable:
  - `claimNext` uses a 10-minute lease and counts attempts.
  - `progress`, `failRequest` and `setWindowCost`.
  - `publishResult` is idempotent per window, selection and run, and marks results that arrive after a correction as outdated.
- **Python client** (`convex` 0.8.1) in `services/api/app/convex_bridge.py`. A retried claim reuses the API's job and result cache, so a retry never pays Claude twice. `tests/test_convex_bridge.py` checks this.
- **Access**: each submission has a review code, stored only as a SHA-256 digest and compared in constant time. The display name is a label, not an account.

Not used: Convex Auth and the Workflow component. Workflow was assessed; see `docs/DECISIONS.md`. The demo uses the cloud dev deployment `proficient-cheetah-424`. The website and the video files stay on this machine. Building this does not establish eligibility for the Convex prize.

## Footage and limits

- The clips stay local. The stadium clip's source is unconfirmed. The Versailles clip is CC BY-SA 4.0 by Manchesterunited1234. Utrecht v Ajax is CC BY 3.0 by FCUFAN and is mostly crowd; it is not the scouting proof. See `fixtures/RIGHTS_MANIFEST.json`.
- A YouTube download is allowed only for the team's own upload or a video YouTube marks Creative Commons (Filters, then Features, then Creative Commons). A standard-licence match video is not usable. Ultralytics, used for detection, is AGPL-3.0.
- The 20-second stadium scout did not produce a classified action. The player was lost after about one second, and the ball was not with him in that span. A longer continuous clip is still required before the automatic brief can be judged.
- Each clip supports one window where the player can be followed. Stadium window 2 (7–14 s) has several same-kit players contesting a header while the camera pans, so it is left unprepared and the summary says so.
- `EVIDENCE_PROVIDER=synthetic` serves a labelled plumbing fixture and is opt-in. A failed Claude call never falls back to it.
- Built with Cursor (AI coding assistant), Next.js, FastAPI, FFmpeg, OpenCV CSRT, Convex and Anthropic Claude.
