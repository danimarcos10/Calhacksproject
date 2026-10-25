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
Upload up to six short clips of one player -> mark the player once in each clip -> inspect evidence -> correct/review -> see one profile (evidence confidence, an unverified ability estimate, and a description) -> request missing footage locally.
M0 is the first upload-to-evidence slice. M0.5 makes one observation checkable for a selected player before M1. M1 adds durable reviews/revisions. M2 completes the same journey. Exact gates are in docs/01_BUILD_PLAN.md.

M1 journey (coach review): open a player submission, watch its evidence moments in sequence, accept, reject or correct each one, and see the saved review summary update in every open session. Preparation (sampling, boxing the player, proposing locations) is a separate page.

M2 journey (automatic first pass): upload a continuous stretch, identify the player once, and receive a brief, an action inventory, and a filterable timeline. The 2–5 minute acceptance run is unmet: no licensed continuous stretch of that length is on disk. The 20-second stadium run tracks, stops when the player is lost, and does not invent a finding.

## Cut list
Full-match analysis, automatic cross-match identity, player rankings, scholarship odds, scouting marketplace, agent search, brand sponsorship pitches, payments, voice and unrelated sponsor APIs. For M1 also: the multi-player dashboard, the comparison view, rendered MP4 export, user accounts, and a second evidence provider.

The scout review can continue into coach outreach. The player confirms position, graduation year, state, league and their email. A fixed league rule chooses NCAA Division I and Division II, or Division II only. Apify reads the public program list and each program's coaches page. A card keeps a coach only when the name, title and email are printed on that page. The email is a stats table from the reviewed clip plus two sentences whose numbers come from that table. Send delivers it from the app's Gmail, with Reply-To set to the player. Test mode is the default and routes every email to MAIL_TEST_TO. The product does not decide a scholarship or name an agent.

## Stack
Checked against hack-stack on 2026-10-25. The journey was already chosen; this pass did not reopen ideation.

- anthropics/anthropic-sdk-python: in the catalog. Calls Claude from the Python API. About 10 minutes, API key required, MIT. Install: `pip install anthropic`.
- Next.js/TypeScript: not in the catalog. Already chosen for the review UI. npm 16.4.3 exists. No key.
- FastAPI/Pydantic: not in the catalog. Already chosen. PyPI fastapi 0.162.0 exists. No key.
- FFmpeg/ffprobe 7.1: not in the catalog. Already installed. No key.
- SQLite via the Python stdlib: not in the catalog. Keeps the demo on one machine. The catalog's Supabase option needs an account, so it stays out.

Manual anchors first. SAM 2.1 and Jev stay off until the core loop works. No Redis, Celery, vector database, scraping, auth, or payments.

hack-stack pass on 2026-10-25 02:50 UTC for M1:
- get-convex/convex (`convex` 1.48.0 npm, `convex` 0.8.1 PyPI): not in the catalog, verified against docs.convex.dev. It is the backend for the shared coach review: submissions, windows, target revisions, the analysis queue, versioned analysis records, decisions, notes and footage requests. Live queries update every open review session. The cloud dev deployment is proficient-cheetah-424 (team daniel-bc765, project secondlook).
- ultralytics 8.4.188 with torch 2.5.1+cu121: not in the catalog. Official track mode docs (https://docs.ultralytics.com/modes/track) specify BoT-SORT for camera-motion compensation. YOLO26n runs on the RTX 3050 Laptop. Licence AGPL-3.0. Used only as the local detector; identity is decided in `services/api/app/scout/identity.py`.
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
- Fit is a league rule, not a prediction. A high-school listing lines up with Division II, other Division I is one step up, and ACC, Big Ten, and Big East are a reach. The rule does not say a player will or will not be recruited.
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
- 2026-10-25 06:05 UTC. M2 path runs. Scores unchanged. The 2–5 minute acceptance criterion is unmet: Utrecht v Ajax (CC BY 3.0, FCUFAN) has about 22 seconds of pitch, and the stadium clip is 20 seconds. On that clip the solid-blue player locked at 1.0 s, the track stopped at about 2.0 s, a correction click resumed it, and it stopped again by 2.1 s. Zero candidates, no new Claude call, empty brief. Spend remains $0.1805 over 6 calls. No cached replay, because there were no classified events.
- 2026-10-25 ~08:00 UTC. The scout review continues into a public-page handoff. Apify search and crawl stay on the same screen. Outreach that sends mail, looks up agents, or decides a scholarship stays cut.
- 2026-10-25 ~09:45 UTC. Coach outreach replaces the generic pathway cards. Apify reads the Wikipedia Division I and II lists and the coaches page it finds for each chosen program. The app can send one email per coach from its own Gmail. Test mode is the default, a coach is emailed at most once per review, and a review can send at most 5 live emails. Scholarship decisions and agent search stay cut.
- 2026-10-25 08:35 UTC. Scout tracking is the Roboflow football player and ball weights plus ByteTrack, cached on upload. The demo clip is the 30-second broadcast sample `dfl-0bfacc_0.mp4` (rights unconfirmed, not for publishing). 375 frames, 23.1 players per frame, ball on 90 percent of frames, 282 seconds to track. One clicked player stayed tracked 29.5 seconds with no loss: 3 receives, 2 completed passes, 1 carry, 1 loss. One text Claude brief reconciled $0.004376 (1,003 + 237 tokens). A repeat reused the brief at no charge. SoccerTrack 118577 missed the 18-player gate (12.6 per frame, 5.8 seconds a frame), so it was not tracked and precision and recall were not computed. The pitch minimap was not built. The stadium review still renders. Ledger reconcile sum is $0.268054.
- 2026-10-25 10:20 UTC. A scout submission can take up to six clips. Tracking runs one clip at a time. When every clip finishes, one text Claude call writes the profile. Evidence confidence is computed in code. The ability estimate is labelled unverified and stays hidden below confidence 40. Player rankings and scholarship odds stay cut. The same broadcast file can be split into three 10-second clips for the demo; each part is one match, not three matches.
