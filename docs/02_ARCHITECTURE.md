# Architecture: one UI, one API, one worker

## Components and boundaries
| Component | Responsibility | First implementation |
| --- | --- | --- |
| Next.js web | Upload, selection, video playback, review, profile | React + TypeScript; native video and canvas |
| Convex (from M1) | Shared review state: players, submissions, windows, selections, analysis queue, runs, observations, decisions, notes, footage requests | Live queries and transactional mutations in `apps/web/convex`; review code per submission; worker functions gated by `WORKER_SECRET` |
| FastAPI API | Validate requests, serve media and frames, tracker proposals, enqueue work | Pydantic models; explicit routes |
| Single worker | FFmpeg jobs and model calls outside request handling | One thread reading SQLite jobs; a bridge thread claims Convex requests and publishes results |
| SQLite | Media, manifests, frames, execution jobs, budget ledger, result cache, worker copies of selections | WAL mode; short transactions; local disk |
| Local object store | Original videos, derivatives, manifests, responses | Generated IDs under DATA_DIR |
| Vision provider | Produce candidate visual observations | Anthropic adapter; configurable model |
| Tracking adapter | Produce proposed target masks/boxes | Manual by default; SAM 2.1 if spike passes |

The browser submits work to the API. The API commits a job and returns its ID. The worker reads only committed jobs, writes a versioned result, and updates status. The browser polls. Media URLs are served by the API with seeking support, not loaded from a worker's filesystem path.

For the first 90 minutes, a bounded in-process task can be acceptable if marked as temporary and interruption is visible. By M1, use a separate worker process and persistent job records. Do not use an untracked fire-and-forget coroutine as the final queue.

M1 boundary, as built: the coach review reads and writes only Convex. The Python bridge (`services/api/app/convex_bridge.py`) polls `worker:claimNext` with the worker secret. For each claim it makes or reuses an immutable SQLite copy of the selection, keyed by the same `rev_` key, runs the existing job with idempotency key `cvx:{request}:{attempt}`, sends stage changes with `worker:progress`, and finishes with `worker:publishResult` or `worker:failRequest`. A retried or expired claim reuses the job, or the result cache keyed by input fingerprint, so it does not pay Claude again. Convex decides whether a result is current: a result for an old selection is stored as outdated and never shown as current.

## Why this stack
Python keeps video handling and model validation together; TypeScript gives a responsive reviewer interface. SQLite avoids cloud-account setup while retaining real persistence. FFmpeg gives explicit media transformations. Claude is both a multimodal component and the strongest directly relevant sponsor-credit fit. The difficult engineering remains visible without a large infrastructure footprint.

Use a familiar alternative if the developer already has a working starter. Do not migrate from a functioning stack merely to match this document. A Python-first team can keep the same contracts in a simpler UI, but must still support accurate player selection and evidence playback.

## Upgrade boundaries
Define ObjectStore, EvidenceProvider, Tracker, and JobRepository interfaces without building a framework. Later, replace local files with private Blob Storage and SQLite with PostgreSQL. Do not dual-write databases during the hackathon. Keep Redis, Celery, Kubernetes, authentication platforms and a vector database out of P0.

Deployment constraint: a single-machine SQLite architecture requires durable local storage and one worker. Ephemeral serverless filesystems and independent replicas are not interchangeable with it.

---

# Project layout and context discipline

## Proposed project layout
```text
secondlook/
  AGENTS.md                 # short invariants
  .cursor/rules/00-project.mdc
  skills/                   # one folder per skill; open only when needed
  .env.example
  apps/web/                 # Next.js application
  services/api/app/
    main.py                 # HTTP entry point
    schemas.py              # authoritative Pydantic models
    db.py                   # transactions and migrations
    worker.py               # single durable job consumer
    media.py                # ffprobe, FFmpeg, manifests
    evidence.py             # semantic validation + rollups
    providers/anthropic.py
    providers/jev.py        # optional; disabled
    tracking/manual.py
    tracking/sam2.py        # optional; disabled
  tests/                    # focused contract/integration tests
  fixtures/                 # synthetic cases + rights manifest
  docs/                     # product spec + state
  data/                     # ignored videos, frames, SQLite
```

Pydantic is the contract source. Generate or derive TypeScript API types from OpenAPI after the routes stabilize; do not maintain two independently invented definitions. Model-generated IDs are not trusted database keys: the server assigns persistent observation IDs after validation.

## Context rules
AGENTS.md is the only always-on project brief. Read one file in docs/ for the task in front of you. Do not preload the set. Keep videos, frames, node_modules, and virtual environments outside indexing. An ignore file is a noise control, not a security boundary for secrets.

## Skills
Skills are folders under skills/. Each SKILL.md has a one-line description and is read only when that description matches the task. Do not copy them into .agents/skills or .claude/skills.

---

# Configuration and dependency decisions

## Environment contract
```dotenv
# Server-side only. Fill locally; never paste keys into chat.
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-5-5
DATA_DIR=./data
DATABASE_URL=sqlite:///./data/secondlook.db
APP_ORIGIN=http://localhost:3000
API_ORIGIN=http://localhost:8000
MAX_UPLOAD_MB=200
MAX_VIDEO_SECONDS=90
MAX_WINDOW_SECONDS=8
MAX_FRAMES_PER_CALL=24
MAX_MODEL_CALLS_PER_JOB=3
APP_BUDGET_USD=15
JOB_BUDGET_USD=1
TRACKER_BACKEND=manual
ENABLE_JEV=false
TYPESAFE_API_KEY=
JEV_MODEL=jev-1.14.0
ALLOW_REPLAY=false
```

These are proposed application defaults, not provider limits. The model IDs were checked against current official documentation; verify account access at startup. If a model is unavailable, select an available image-capable model, record it in the run metadata and recheck pricing. Never silently replace a failed live analysis with a fixture. [S09, S12]

## Dependency policy
Use a supported Node LTS compatible with the installed Next.js release and Python 3.11 for the API, subject to the selected tracking package's requirements. Prefer the current official create-next-app scaffold and standard FastAPI packages. Lock the versions that actually install. Do not spend time assembling an exotic monorepo toolchain.

Backend core: fastapi, uvicorn, pydantic, python-multipart, anthropic, Pillow, pytest and a minimal SQLite access layer. FFmpeg is an OS executable, not a replacement Python package. Use subprocess argument arrays with shell disabled. Add OpenCV or PyTorch only for a feature that survived the relevant spike. Avoid installing multiple conflicting OpenCV wheels.

## Startup checks
- Confirm writable DATA_DIR, executable ffprobe, reachable API and a supported media codec.
- Validate key presence without revealing it; report provider authentication failure separately from video failure.
- Use exact development CORS origins. Production should prefer a same-origin reverse proxy or explicitly configured trusted origins.
- Expose /healthz for process health and /readyz for required capabilities; missing optional providers must not make the core unready.
- Commit .env.example and lockfiles. Ignore .env files, data, checkpoints and caches. Never expose private provider keys through NEXT_PUBLIC variables.
