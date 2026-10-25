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
