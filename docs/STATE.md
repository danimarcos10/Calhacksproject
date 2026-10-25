# Current state

Status: M1 coach review is done and browser-verified. All work since M0 is uncommitted.

Open `http://localhost:3000/review/sub_32eb531dc1444352` in a browser that has used the stadium review link. The link is printed by `scripts/seed_review.py`; the code lives in that browser.

Stadium window 1 (0–7 s) is on selection 2, a labelled correction. It has hand boxes on f01–f04, f07 and f10, tracker estimates on f08 and f09, and f05 and f06 marked uncertain. Its current run made two observations, both accepted:
- A passing moment, 0–1.084 s.
- An off-ball movement moment, 3.237–4.838 s.

The selection 1 passing moment is stale and kept in history. Window 2 (7–14 s) is unprepared: same-kit players contest a header during a pan. Versailles is a separate player with zero observations.

Convex runs on a local deployment at `http://127.0.0.1:3210`. A cloud deployment needs `npx convex login` in `apps/web`, then `scripts/convex_setup.py` and `scripts/seed_review.py`.

Verified this session:
- pytest: 34 passed.
- vitest: 25 passed.
- `tsc --noEmit`: clean.
- `scripts/check_convex.py`: 11/11.
- Browser: playback, accept, refresh and a restart of both backends, two-session reject and footage request, correction stale in both tabs, re-analysis without the stale moment returning.

Spend: one paid call in M1 ($0.04559). Project total $0.1805 over 6 reconciled calls.

Run from `secondlook/`:
- `npx convex dev` in `apps/web`.
- The API: `services\api\.venv\Scripts\python -m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8000`.
- `npm run dev` in `apps/web`.

Open questions:
- No coach has tried it.
- The Devpost rule "Team required: 2 to 4 members" against a solo entry.
- The Convex prize amounts conflict.
- The stadium clip's rights are unverified, so it stays local.

Next: a backup video, one person trying the review, then commit when asked.

Time: 04:10 UTC, deadline 16:00 UTC.
