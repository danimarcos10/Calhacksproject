# SecondLook / Cal Hacks 13.0

## Event
- Deadline: 2026-10-25 09:00 America/Los_Angeles = 16:00 UTC. Recompute time remaining now; current organizer changes override this snapshot.
- Judging: in-person expo; prepare a 2-minute core and 30-second version. Confirm the exact slot onsite.
- Criteria: application/intentionality, functionality, creativity, technical complexity.
- Targets: Anthropic Public Benefit if community need is validated; Microsoft real-world/customer-impact; relevant general awards. Optional tracks require actual implementation.
- Convex Best Use is an explicit target from 2026-10-25. The Devpost listing (read 02:50 UTC) says "$5,000 cash to the winning team" and "Use real Convex features like live queries and components to win." Eligibility and winning are not established by building it.
- The same Devpost page says "Team required: 2 to 4 members" and lists a Best Solo Hack prize. This build is solo. Confirm with organizers before submitting. Judging there is a 3-minute pitch plus 2 minutes of questions, and a demo video is needed for sponsors judging asynchronously.

## Team
- Assume one builder until the user provides team context. No skill session should restart an unnecessary questionnaire.

## Problem
- Hypothesis: a coach reviewing submissions needs traceable evidence and specific gaps; public-school players without paid recruiting support may benefit.
- User/customer validation: pending. No coach endorsement or scholarship outcome is established.
- Distinct demo: source-linked observations, explicit uncertainty, and corrections that update a multi-clip profile.

## MVP journey
Upload short footage -> mark player/window -> inspect evidence -> correct/review -> see current multi-clip coverage -> request missing footage locally.
M0 is the first upload-to-evidence slice. M0.5 makes one observation checkable for a selected player before M1. M1 adds durable reviews/revisions. M2 completes the same journey. Exact gates are in docs/01_BUILD_PLAN.md.

M1 journey (coach review): open a player submission, watch its evidence moments in sequence, accept, reject or correct each one, and see the saved review summary update in every open session. Preparation (sampling, boxing the player, proposing locations) is a separate page.

## Cut list
Full-match analysis, automatic cross-match identity, player rankings, scholarship odds, scouting marketplace, outreach, payments, voice and unrelated sponsor APIs. For M1 also: the multi-player dashboard, the comparison view, rendered MP4 export, user accounts, and a second evidence provider.

## Stack
Checked against hack-stack on 2026-10-25. The journey was already chosen; this pass did not reopen ideation.

- anthropics/anthropic-sdk-python: in the catalog. Calls Claude from the Python API. About 10 minutes, API key required, MIT. Install: `pip install anthropic`.
- Next.js/TypeScript: not in the catalog. Already chosen for the review UI. npm 16.4.3 exists. No key.
- FastAPI/Pydantic: not in the catalog. Already chosen. PyPI fastapi 0.162.0 exists. No key.
- FFmpeg/ffprobe 7.1: not in the catalog. Already installed. No key.
- SQLite via the Python stdlib: not in the catalog. Keeps the demo on one machine. The catalog's Supabase option needs an account, so it stays out.

Manual anchors first. SAM 2.1 and Jev stay off until the core loop works. No Redis, Celery, vector database, scraping, auth, or payments.

hack-stack pass on 2026-10-25 02:50 UTC for M1:
- get-convex/convex (`convex` 1.48.0 npm, `convex` 0.8.1 PyPI): not in the catalog, verified against docs.convex.dev. It is the backend for the shared coach review: submissions, windows, target revisions, the analysis queue, versioned analysis records, decisions, notes and footage requests. Live queries update every open review session. A local deployment provisioned without an account in about 4 minutes. A cloud dev deployment needs `npx convex login`.
- @convex-dev/workflow: assessed after the core worked and deferred. The paid step runs in the Python worker, outside Convex, and the lease, attempt key and result cache already make retries free. Reason in docs/DECISIONS.md.
- The Python media, sampling, CSRT and Claude pipeline stays. Python connects out to Convex with a worker secret, so no hosted function needs to reach localhost.

```text
coach review page --live query/mutations--> Convex (review state, queue, analysis records)
prepare page --frames, proposals--> FastAPI -> SQLite execution jobs, budget, cache
                                            -> local MP4/frames -> one Claude vision call
Python worker --claim, progress, publish (worker secret)--> Convex
```

Riskiest assumption: a useful, correctly attributed observation from about two frames per second of a distant fullback. Spike that on a real clip before adding surface area.

## Honesty
- The coach hypothesis is unvalidated. No coach has used this, and no scholarship outcome is claimed.
- `fixtures/synthetic/` is generated colour, not football. `EVIDENCE_PROVIDER=synthetic` is opt-in. The 2026-10-25 browser walkthrough used it because no API key was set. The page showed "SYNTHETIC FIXTURE, not football analysis." A provider failure does not switch to it.
- The review clip is CC BY-SA 4.0 by Manchesterunited1234, kept local. `can_publish` is false. Attribution is required if it is shown. Adult status is "professional senior league per title, not individually verified."
- One live Claude call succeeded on 2026-10-25: `claude-sonnet-5-5`, 14,326 + 741 tokens, $0.036062, 11.1 s, zero observations. Summary in `data/replay/claude-versailles-0-8s.json` (not replayed; `ALLOW_REPLAY` is false). The earlier browser cards ($0.0006, 100+40 tokens) were the synthetic fixture.
- M0.5 live calls, same model, prompt `evidence-v2`: the stadium clip (`vid_c4a22427e7144ee2`, 0–7 s, player in solid blue number 11) returned one passing action, outcome not observable, $0.040526, 15.4 s. The Versailles window with one distant box returned zero observations, $0.03441, 7.9 s. The new clip's license is unconfirmed (Pexels returned 403); `can_publish` is false. Three retries of the first attempt were cut off by the 1,500-token cap and released locally with no stored token total. One later truncated call is recorded at $0.023322 (11,661 input tokens, 0 output). A request that tried to disable thinking was rejected and released. Recorded reconciled cost for the two M0.5 successes plus that truncated call is $0.098258.
- Prices in config are a snapshot of $2 / $10 per million tokens. No new paid infrastructure was started.
- M1 correction demonstration is constructed, not a model mistake found in use. The first stadium analysis said f02 and f03 had no box. In correction mode I drew boxes on f02 and f03 by hand. I took tracker estimates on f05, f06, f08 and f09: f05 and f06 stayed uncertain because the tracks disagree, and f08 and f09 stayed estimated. I cleared f11 to f14 because the one-direction track had drifted onto empty grass. Saving made selection 2 and turned the accepted passing moment stale in both sessions. One live re-analysis (`claude-sonnet-5-5`, 13,855 + 1,788 tokens, $0.04559, 18.6 s) returned a passing moment and an off-ball movement moment. Both were checked against frames and accepted.
- The two-session demo used two tabs of one browser on the local Convex deployment. The display name lives in that browser's localStorage, so both tabs share it unless changed; selection 2 was saved under "Coach B" for that reason. Review codes are the only access control; there are no accounts.
- Reloads, both backend restarts and the two-session steps made no paid call; the budget ledger did not change. Actual Claude spend for the project is $0.1805 over 6 reconciled calls. Four further attempts were released with usage unknown.
- Each clip supports one attributable window. Stadium window 2 is sampled but not prepared, and the summary says it was not analysed. The Versailles analysis returned zero observations and the review shows none.

## Pitch
SecondLook helps coaches inspect the evidence behind submitted footage and identify what they still need to see. Roles assumed solo until assigned.

## Status log
- Planning kit prepared 2026-10-24. Next: verify clock/key/footage and build M0. No implementation acceptance gates have passed.
- 2026-10-25 ~00:00 UTC. hack-scope refine, no questionnaire. Deadline 16:00 UTC. About 16 hours were left at 23:50 UTC; reserve the last 90 minutes for submission and demo. Solo. One journey: upload a short clip, mark the fullback and a 6-8s window, read source-linked candidate observations or an honest gap. Judging check at scope time: application pass (a coach, at the moment of reviewing submitted footage); functionality fail until M0 runs; creativity pass (provenance and abstention, not a rating); technical complexity pass only if the timestamp and citation path is real. Cut list unchanged.
- 2026-10-25 ~00:00 UTC. hack-stack confirmed the stack above. Skills under .agents/skills match third_party/calhacks-kit/SHA256SUMS (12 files). Event preset in hack-scope/events is older; HACK.md and docs/08_SPONSORS_AND_COSTS.md win.
- 2026-10-25 00:37 UTC. hack-check, phase Build (about 15h 23m left). Weakest criterion: functionality, because the real model call has not run. Next action: add ANTHROPIC_API_KEY and repeat the 0–8 s fullback window on Claude. Anthropic track is not met until that call exists. No cut-list work was added.
- 2026-10-25 00:57 UTC. Live `claude-sonnet-5-5` call on the 0–8 s window succeeded with zero observations and stated gaps. Anthropic track now has one real call.
- 2026-10-25 02:03 UTC. M0.5: four manual boxes on the solid-blue player produced one checkable observation. Unknown name did not suppress it. Versailles stayed an honest gap. M1 is not started.
- 2026-10-25 02:50 UTC. hack-check, phase Build (13h 10m left; Harden rules from 04:00 UTC, journey work still allowed). Scores: Application 2 (one observation, no review flow), Functionality 3 (live analysis works, decisions are not saved), Creativity 3 (provenance and abstention; correction invalidation not shown), Technical complexity 3 (validated timestamps, CSRT; no shared state). Weakest: Application. Next: Convex-backed coach review with two-session live updates. Convex track not met yet: only the package is installed. Anthropic track has real calls. M0.5 work is uncommitted.
- 2026-10-25 04:05 UTC. hack-ship pass. Secret scan clean: no tracked `.env`, no pattern match in 138 committable files or in history, and the exact Anthropic key, worker secret and review codes appear nowhere committable. README rewritten with value prop, architecture, three-process setup, checks, Convex explanation and limits. Checklist gaps: no live URL (local only), no backup video, no coach feedback, team-size rule unconfirmed.
- 2026-10-25 04:10 UTC. hack-check, phase Harden (11h50m left). Scores: Application 3 (full coach review on real footage; coach need unvalidated), Functionality 4 (browser-verified persistence, restarts, two sessions, correction and re-analysis; local only), Creativity 4 (evidence playlist, stale-on-correction in every session, honest gaps), Technical complexity 4 (leased Convex queue, idempotent publish, per-window staleness, CSRT, exact timestamps). Weakest: Application. Next: record the 60–90 s backup video of the review flow and put it in front of one coach or teammate. Convex track has a real integration; eligibility unverified. M1 work is uncommitted.
- 2026-10-25 05:10 UTC. hack-check, phase Harden (10h 50m left). Scores unchanged: Application 3, Functionality 4, Creativity 4, Technical complexity 4. Weakest: Application. The committed journey is now M2, automatic first-pass scouting of longer footage; dashboards, comparison, scholarship and outreach stay cut. Next: commit the M1 checkpoint, then one player selection to a live scouting brief. Secret scan of 224 files found no key, worker secret or review code. pytest 34, vitest 25, tsc clean.
