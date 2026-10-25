# Initial Cursor prompt: setup and operating rules

You are building SecondLook, a football recruiting evidence reviewer for Cal Hacks 13.0. Establish the project directory and implement the first real working milestone now. Do not stop after scaffolding or a plan.

Use the attached/extracted SecondLook_Cursor_Kit as the specification. If this workspace already contains AGENTS.md, HACK.md and docs/, use this folder as the project root. If the kit is beside an empty workspace, create secondlook/ and copy the kit into it. Inspect existing files first, preserve unrelated work, and do not create a nested app accidentally. If only the PDF is available, create the same small Markdown context structure from it before coding.

Read AGENTS.md, HACK.md, docs/STATE.md and docs/01_BUILD_PLAN.md. Then read only the architecture, video, contract and AI sections needed for M0. Do not load the whole PDF or every document on every turn. Keep STATE.md under 300 words with verified behavior, commands, blocker and next task. Put durable decisions in DECISIONS.md.

The six original George Kalangi skills are in .agents/skills/hack-*/ with supporting files. Verify they are discoverable. Use hack-scope and hack-stack to check the already-chosen journey; do not restart ideation or ask questions already answered in HACK.md. Use hack-check after M0. Current event sources in docs/08_SPONSORS_AND_COSTS.md and HACK.md override the older bundled event preset. If the skills are missing, obtain the original calhacks-kit at commit 209a9095e6dc0771596dabdf77cc604d0959a70e, copy its skills/ into .agents/skills/, and preserve LICENSE and provenance. Do not invent replacement skills.

Check the actual time against Sunday 2026-10-25 09:00 America/Los_Angeles (16:00 UTC). Adjust scope to the remaining time and leave at least 90 minutes for submission/demo preparation. Default to solo ownership unless existing context establishes teammates. Make routine implementation choices and continue; ask only for a genuinely blocking missing input.

Build with Next.js/TypeScript in apps/web and Python FastAPI/Pydantic in services/api. Use FFmpeg, SQLite and local files first. Keep provider keys server-side. Use a configurable image-capable Claude model; the checked default is claude-sonnet-5-5, but verify account access and installed SDK support. Lock the versions that actually work. Do not add cloud auth, payments, Redis, Celery, a vector database, scraping, Jev or SAM 2 until the core loop works.

---

# Initial Cursor prompt: implement and verify M0

M0 must do all of this:
1. Accept a local MP4/MOV upload with a proposed 200 MB/90-second cap. Probe and validate it, persist it by generated ID, and play it in the browser with working seeking.
2. Let the user choose a 6-8 second interval and mark the target on sampled frames. Normalize boxes correctly through resizing/letterboxing/rotation. Allow target-not-visible and identity-uncertain states.
3. Extract ordered timestamped frames with a manifest mapped to source playback time. Do not derive source timestamps from assumed constant frame rate.
4. Make one real Claude call through a provider adapter using a versioned prompt and structured Pydantic output. Validate all referenced frames, intervals and target revisions. Zero supported observations is valid.
5. Display candidate evidence cards with visible action, source interval, limitations and review state. Clicking a card seeks the source video. Never invent ability ratings, match statistics, scholarship odds or an observed outcome that is not visible.
6. Show real job stages and friendly failures. Preserve the upload and selection on retry. Store model/version/usage metadata. Bound calls and costs. A real provider failure must not silently switch to a fixture.

Use a plain but clean review layout. Spend time on the playable video, target selection and evidence interaction before visual polish. If no key or real footage exists, finish the independent upload/selection/validation work, make the missing prerequisite explicit, and keep a separate labeled synthetic fixture for plumbing tests. Do not call M0 complete until a real video-to-provider-to-evidence run succeeds.

Run focused checks for coordinate mapping, timestamp/citation validation, rejected malformed output and one browser walkthrough. Record exactly what ran and what remains unverified. Do not claim tests or live inference passed without executing them.

Deliver the working M0, exact setup/run commands, a concise account of verified behavior and blockers, and the single next milestone. Update HACK.md and STATE.md. Stop at that mentor-review checkpoint rather than starting optional integrations. The full 15-hour plan is in the docs for subsequent turns. Do not send messages, publish footage, incur new paid infrastructure charges or submit to Devpost as part of this initial build prompt.

---

# Follow-up prompts for each checkpoint

## After the first mentor review
“Read STATE.md, HACK.md and the current diff. Summarize what actually works in five lines. Incorporate these mentor notes: [paste notes]. Keep the committed workflow. Implement M1: durable jobs, accepted/rejected/stale observation states, player-anchor correction, revision invalidation and rerun. A stale worker must not overwrite a newer selection. Verify the correction flow end to end and update STATE.md.”

## Optional tracking spike
“The M0 loop works. Timebox tracking to 60 minutes. Inspect whether a suitable GPU and the official SAM 2 requirements are already available. If they are, test SAM 2.1 Small on the same short selected windows, with point/box prompts and correction. Measure setup and runtime; visually inspect crossing/occlusion failures. Keep the manual adapter working. If the spike does not pass the documented gate, disable it and continue with manual anchors. Do not train a model.”

## Complete the profile workflow
“Implement M2 using current accepted observations only: multiple clips, declared match grouping, deduplicated intervals, evidence coverage by category, an inbox, a two-submission comparison and a local request for missing footage. Use deterministic counts and source links. Do not add talent scores or new providers. Demonstrate that correcting a source claim changes the profile after refresh.”

## Run an honest evaluation
“Read docs/07_VALIDATION.md. Create the smallest meaningful audit using available permissioned footage and a held-out example where possible. Test citation integrity, wrong-player correction, overlapping windows, duplicate input, interruptions and provider failure. Report raw counts, actual latency/cost and unresolved failures. Do not infer population accuracy or time savings from targets in the plan.”

## Freeze and ship
“Run the bundled hack-check and hack-ship against the real deadline. No new features. Verify README setup, media playback, permissions, secret handling, sponsor claims and public-link access. Draft the submission and a two-minute script from implemented behavior. Record a real backup video. Mark every live, cached, manual and synthetic element. Prepare the final files; do not send or submit anything without the user's instruction.”

## Resume after a context reset
“Read AGENTS.md, HACK.md and docs/STATE.md. Check git status and the latest working command. Continue the single next task recorded there. Load only the relevant technical document. Do not re-scope the project, re-install working dependencies or replace a functioning architecture without concrete evidence of a blocker.”

These prompts assume each previous acceptance gate actually passed. If it did not, finish or shrink that gate first. A milestone name in STATE.md is not evidence that the feature works; the run log and observed behavior are.
