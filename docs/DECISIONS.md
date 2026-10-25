# Decisions

- 2026-10-24: Build a video evidence reviewer with human correction; no automated recruitment decision.
- Start with one fullback and short selected windows. Expand to multiple clips after real M0.
- Use a local Python media backend and TypeScript UI. Cloud setup is outside the first milestone.
- Claude is the primary visual model. SAM 2.1 is optional tracking; Jev is text-only optional routing.
- Use evidence categories and coverage, not arbitrary ability ratings. Missing evidence remains unknown.
- Snapshot event sources override the mentor kit's older event preset. Verify live changes before submission.
- The PDF is the complete reference; selective Markdown context is the everyday agent interface.

Append only durable changes with a reason. Do not paste chat transcripts.

- 2026-10-25: Project root is `secondlook/`, copied from SecondLook_Cursor_Kit. The original kit folder stays untouched. Python is 3.12.6 because this machine has no usable project-local 3.11.
- Browser calls the API directly. CORS allows only APP_ORIGIN. Provider keys stay in the API process.
- Every upload gets an H.264 playback copy with the display rotation applied, so MOV and phone video seek in the browser. Analysis frames are sampled from the original, with the same rotation applied, and their times come from decoded presentation timestamps minus the first displayed frame. Frame index divided by frame rate is not a timestamp.
- M0 ingest transcodes inside the upload request. The job worker is one in-process thread and is temporary until M1. A job still running when the process starts is marked interrupted; the user retries. It is not resumed in secret.
- Manual anchor boxes are drawn onto a copy of the JPEG sent to the model and labelled as a manual coach anchor. The frames shown in the UI stay clean.
- A synthetic provider exists only when EVIDENCE_PROVIDER=synthetic. A live provider failure never selects it.
- Tests live in services/api/tests and apps/web (vitest). Dependency versions are the ones that installed, recorded in the lock files.
- Locked after install: FastAPI 0.162.0, Starlette 1.10.0, Pydantic 2.14.1, anthropic 2.3.0, Pillow 13.0.0, Uvicorn 0.54.0, Next.js 16.4.3, React 19.3.0, Vitest 5.0.5, openapi-typescript 7.13.0. FFmpeg is the machine's 7.1 build.
- Frame extraction uses `-copyts`. On FFmpeg 7.1 the select filter's `t` otherwise starts at zero even when the container timestamps do not, so the exact-frame select would miss an offset clip.
- 2026-10-25: M0.5 drops the default fullback role and the clip-wide identity-uncertain hold. Continuity is per cited frame. Prompt `evidence-v2` and schema `1.1` change the cache key. Output budget is 4,000 tokens because this model spends part of that budget on thinking and a 1,500 cap truncated the JSON. Thinking could not be disabled on this model. SAM 2 stays out. CPU CSRT proposals are kept only where both directions agree; one-direction tracks are flagged, not presented as located.
- 2026-10-25 M1: Convex (1.48.0, pinned) is the backend for review state; the user made Best Use of Convex a project priority. The Python media, tracking and Claude pipeline stays. Each field has one owner (table in `docs/04_CONTRACTS.md`). SQLite keeps media, jobs, budget and cache, and immutable worker copies of selections keyed by the Convex `rev_` key.
- The worker connects out to Convex with `WORKER_SECRET`, a deployment environment variable set from a temporary file by `scripts/convex_setup.py`. The value is never printed or committed. Hosted functions never call the laptop.
- Access is a per-submission review code. Convex stores only its SHA-256 digest and compares in constant time. The reviewer name is a display label in localStorage. Accounts stay on the cut list; the code is the scoped access for a two-person demo.
- Observations are immutable and decisions are append-only, tied to the observation and its selection number. Moment status is derived at read time, so a correction needs no rewrite of old records: it moves the window's current selection and the old run stops being current.
- Retry safety: a claim has a 10-minute lease and an attempt counter. The bridge job key is `cvx:{request}:{attempt}`. The API's active-job dedupe and fingerprint cache stop a retried claim from making a second paid call. `publishResult` is idempotent per window, selection and run key.
- Workflow component (`@convex-dev/workflow`) assessed and deferred. Its action retries and `awaitEvent` would sit in front of a step that runs outside Convex, the Python worker. Retry safety there already comes from the lease, attempt key and result cache. Moving the Claude call into a Convex action would need hosted access to local frames and would make action retries a billing risk. Adopting it would add a component and a second sequencing layer without changing a guarantee. Revisit if review gains multi-step server-side follow-ups, such as a timed footage-request reminder with `step.sleep`.
- Tracker proposals decode into a fresh temporary folder per call and clean up best-effort. OneDrive held a lock on the shared folder, and `rmtree` raised access denied, which reached the browser as "Failed to fetch". File-system errors now return `tracker_failed`.
- The playlist button counts moments and merged segments ("2 in 1 segment"). A bare segment count read as a moment count.
