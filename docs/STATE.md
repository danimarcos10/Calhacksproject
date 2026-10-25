# Current state

Status: local upload, playback, sampling, anchors, and evidence cards work. A real Claude call has not run.

Verified:
- pytest: 18 passed in `services/api` (VFR timestamps against a moving bar, rotation, HTTP 206, upload rejections, citation and revision checks, budget, idempotency, auth failure, missing key).
- vitest: 5 passed for contain-fit geometry. `npx tsc --noEmit` passed in `apps/web`.
- Commons clip `vid_9f25d5e3c9e74b41`, 18.518 s, 1920x1080. The player reached readyState 4. Media requests returned 206.
- Window 0–8000 ms, 16 frames. Revision 1 boxes the blue player on f05 (2.135 s); other frames are marked not visible; identity is uncertain.
- Browser: sample, save, analyze. Stages showed timestamps. The one card spans 0:00.000–0:07.975. Clicking it paused the video and set `currentTime` to 0, matching the card.
- `scripts/check_provider.py` exited 2. `ANTHROPIC_API_KEY` is not set.

Blocker: without a key there is no video-to-Claude-to-evidence run. The walkthrough set `EVIDENCE_PROVIDER=synthetic`. The page banner said it is not football analysis. That run is not the M0 provider gate.

Automation gaps: the file dialog was not driven, so the clip was posted to the API and the page opened at `/?video=`. An untrusted pointer event did not start a box drag; the box was applied through the canvas pointer handlers.

Commands, from `secondlook/`:
- API: `services\api\.venv\Scripts\python -m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8000`
- Web: `npm run dev` in `apps/web` at http://localhost:3000
- Tests: `python -m pytest` in `services/api`; `npm test` in `apps/web`

Next task: put the key in `secondlook/.env`, run `check_provider.py`, and repeat this 0–8 s window on Claude. M1 is next after that: durable jobs, accept/reject, anchor correction, and revision invalidation. M1 has not been started.

Time left: about 15h 23m at 2026-10-25 00:37 UTC. Deadline 16:00 UTC.
