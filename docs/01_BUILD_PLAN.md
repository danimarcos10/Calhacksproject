# Milestones that remain useful if time runs out

## M0: a real vertical slice, by 90 minutes
A user uploads a clip, sees its duration, chooses a 6-8 second window, marks the player on a few sampled frames, and runs analysis. The result is a small set of candidate observations, each linked to a source interval, or an honest insufficient-evidence result. Clicking evidence seeks the playable source video. The UI shows whether the model ran, failed, or is unavailable.

M0 is done only after one real clip reaches a real provider and a returned observation survives schema and provenance checks. A mock response is useful for UI development, but is not the completed AI milestone. If no key or footage is available, report that precise blocker and leave the working upload/selection path available.

## M0.5: a useful player-specific observation

One selected player, a few manual boxes, and one observation a person can check against the frames. Untouched frames stay unannotated. A name is not required. Continuity is per frame. This supersedes the default fullback role, the clip-wide identity-uncertain flag, the M0 instruction to mark first/middle/last, and starting M1 immediately after M0. M1 has not started.

## M1: a credible reviewer, by hours 4-6
Persist submissions and jobs. Show sampled-frame identity markers. Add approve, reject, and correct-player actions. A correction makes dependent observations stale. Re-analysis creates a new revision. Persist the report so refresh and server restart do not erase it. Have three examples ready: clear action, ambiguous action, and wrong-player correction.

As built (2026-10-25): Convex holds the review, and a separate coach view sits beside the Prepare page. Browser-verified:
- Watch moments plays the merged, padded intervals.
- Accept updates the playlist and summary.
- Decisions survive a refresh and a restart of both the API and Convex.
- A reject made in one session appears in the other without a refresh, and so does a footage request.
- The correction demonstration works. Hand boxes were added on f02 and f03, plus tracker estimates. Saving made the accepted moment stale in both sessions. One re-analysis returned two new suggestions, and the stale one did not return.

Each clip supports one attributable window, not three. The wrong-player example became a constructed correction; it is labelled as such.

## M2: the ambitious complete product, by hours 8-9
Two or three clips roll up into a profile with distinct matches, reviewed windows, accepted observations, disputed claims, and gaps. A coach inbox and comparison view reveal evidence coverage without a hidden ranking. “Request more footage” creates a local task stating the missing category and why. All core screens work on a real dataset, and one correction visibly changes the rollup.

## M3: a judging-ready delivery, hours 9-15
Freeze product scope. Test the complete journey, bound latency and costs, create a reproducible run path, optionally deploy if infrastructure is already available, record a real backup demo, and submit. A reliable local demo plus a clearly labeled recorded backup is better than a broken cloud upload flow.

## The impressive moment
Open an apparently favorable passing observation. Play its evidence. Correct the selected player because two same-color shirts crossed. The observation is invalidated; a fresh run now says the action cannot be attributed reliably. The aggregate changes from supported evidence to a gap. The coach can see the reason and original revision.

This demonstrates computer vision plumbing, schema-constrained inference, dependency invalidation, stateful orchestration, and a usable decision workflow. Each part serves the same visible user task. Do not stage a false mistake and present it as a naturally occurring model result; label a deliberately constructed correction scenario.

---

# The 15-hour execution plan

Time estimates are planning targets, not measured performance. Reset the schedule against the real deadline. If a gate fails, take the fallback immediately instead of borrowing all the demo-preparation time.

| Elapsed time | Deliverable and acceptance gate |
| --- | --- |
| 00:00-00:15 | Choose footage, verify key, set deadline, establish repo. One playable local clip and a named target. |
| 00:15-00:45 | FastAPI upload + ffprobe metadata + frame extraction. Inspect actual frames and timestamps before building the report UI. |
| 00:45-01:30 | Next.js selection UI + one real Claude extraction + evidence cards + seek. Gate: M0 works end to end. |
| 01:30-02:00 | Show mentor or coach. Record three concrete reactions. Fix the biggest usability or attribution failure. |
| 02:00-03:00 | If a suitable GPU is already usable, spike SAM 2.1 on one short window. Otherwise improve manual anchor review. Hard cutoff: 60 minutes. |
| 03:00-04:30 | Persist jobs, observations, review states and analysis revisions. Wire correction to invalidation and rerun. |
| 04:30-06:00 | Finish M1 with cross-refresh recovery, ambiguous-video behavior, and an observable end-to-end correction. |
| 06:00-07:30 | Add multiple clips and deterministic evidence coverage. Deduplicate repeated footage; retain per-match provenance. |
| 07:30-09:00 | Finish inbox, evidence comparison, and a local request for more footage. Gate: M2 complete; feature freeze. |
| 09:00-10:30 | Run the evidence audit, fix broken attribution/timestamps, test failures and budget caps. |
| 10:30-12:00 | Deployment only if ready; otherwise strengthen local run and backup. Test from a clean environment. |
| 12:00-13:00 | Record the real demo. Draft Devpost, README, sponsor evidence, and two-minute script. |
| 13:00-14:00 | Rehearse three times. Fix only reproducible demo blockers. Submit a complete entry. |
| 14:00-15:00 | Buffer for links, upload trouble, reviewer access, and final checks. Rest before judging where possible. |

Do not read “15 hours” as fifteen hours of uninterrupted feature work. Meals, brief breaks, integration delays, and mentor conversations belong inside this budget. A teammate enables overlap; it does not justify doubling the product surface.

The mentor's hack-check skill moves into hardening with 6-12 hours left and freeze under 6. Respect that by committing the single journey upfront and dropping optional integrations early. Finishing the committed journey remains the priority; new ideas go to the cut list. [S07]

---

# Compression, ownership, and stop rules

## If less time remains
| Usable time | Build target | What to remove |
| --- | --- | --- |
| 12-15 hours | M2 plus strong demo | All optional providers except an already-working tracker |
| 8-12 hours | M1 plus simple multi-clip summary | GPU setup, rich comparison, cloud migration |
| 4-8 hours | M0 plus review/reject and saved results | Multi-player inbox, deployment, natural-language search |
| Under 4 hours | One real clip, evidence seek, honest limitations, backup | Everything outside that flow |

Reserve at least 90 minutes for submission and a reliable demo even in the compressed plan. The real deadline overrides every estimate in this document. Do not spend the last hour trying to install CUDA or rebuilding the UI framework.

## Stop rules
- Provider blocked for 15 minutes: continue media/UI work; show setup status. Use another already-authorized multimodal provider only through the same adapter, and update sponsor claims. Do not fabricate live results.
- Tracking not useful after a 60-minute spike: disable it. Keep manual anchors and uncertainty. Never ship a smooth marker that silently changes players.
- One feature absorbs 45 minutes without measurable progress: cut or simplify it using hack-check rescue mode.
- Deployment blocks for 30 minutes: preserve the local demo and recorded backup. A hosted frontend pointing at your localhost backend will not work for judges.
- Fewer than six hours to submission: no new scope. Finish or shrink the committed journey, then harden and present.

## Team allocation if people are available
Two people: one owns media, schemas, model orchestration and tests; one owns upload, selection, review, profile and demo. Agree on the API contract before splitting. Three people: the third owns footage permissions, coach feedback, evaluation labels, sponsor verification and submission, then assists QA. Four people: give the fourth the optional tracker only if the core contract is stable.

Do not multiply autonomous coding sessions across the same files. Use explicit ownership, small commits, and a fixed contract. Merge one boundary at a time. Keep a known-working checkpoint before every optional change.

## Evidence at each checkpoint
Update docs/STATE.md with the last working command, verified behavior, current blocker, next task and actual time remaining. Keep it under 300 words. Record failed assumptions in docs/DECISIONS.md. Do not turn either file into a conversation transcript.

---

# The first 90 minutes: tickets Cursor can execute

## Ticket A: boot and probe, 15 minutes
Create apps/web and services/api, an environment example, ignored local data directory, dependency locks, and /healthz. Install FFmpeg through the operating system's supported method; confirm ffmpeg and ffprobe run. Check the model key is present without printing it. Read available model IDs or make a minimal authenticated request. Record the installed versions; do not invent package versions.

## Ticket B: ingest and sample, 20 minutes
POST a local MP4 or MOV as multipart data. Stream it to a generated internal ID, cap size and duration, and inspect it with ffprobe. Return an ID, duration, dimensions, rotation, and a playable media URL. Extract a representative frame and then a bounded window. Save frame timestamps in a manifest. A malformed video yields a friendly error, not an unhandled exception.

## Ticket C: pick the player, 15 minutes
Show video, interval controls, and a canvas over a sampled frame. Save a normalized rectangle and timestamp. M0 asked for first/middle/last anchors and an explicit identity-uncertain flag. M0.5 supersedes that: a frame stays unannotated until the user marks it located, not visible, or uncertain, and a name is not required. Keep controls plain; the player and evidence should dominate the screen.

## Ticket D: one real model call, 20 minutes
Send the window's ordered frames and identity information through the Anthropic adapter. Include source timestamps. Use a small Pydantic output schema and the current SDK's structured-output support. Validate every returned frame ID and time range against the actual manifest. Allow zero observations. Store the model ID, prompt version, token usage and response status.

## Ticket E: display and seek, 15 minutes
Poll the job. Show stage labels tied to real work: validating, sampling, analyzing, validating evidence, complete or failed. Render up to three candidate observations with interval, category, visible action, uncertainty, and review state. Clicking a card seeks the source video. Highlight that these are unreviewed suggestions.

## Ticket F: a literal run-through, 5 minutes
Start from upload, not an already-open result page. Run one real clip, click every returned evidence card, and record the actual elapsed processing time. Try one ambiguous window. Save the real successful response for a labeled replay mode. Write down the exact next improvement before showing a mentor.

If time runs over, simplify layout and manual controls first. Do not remove source validation or hide errors. A functioning unattractive evidence loop is a more useful first prototype than a polished profile filled with invented numbers.
