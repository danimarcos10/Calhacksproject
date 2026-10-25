# SecondLook / Cal Hacks 13.0

## Event
- Deadline: 2026-10-25 09:00 America/Los_Angeles = 16:00 UTC. Recompute time remaining now; current organizer changes override this snapshot.
- Judging: in-person expo; prepare a 2-minute core and 30-second version. Confirm the exact slot onsite.
- Criteria: application/intentionality, functionality, creativity, technical complexity.
- Targets: Anthropic Public Benefit if community need is validated; Microsoft real-world/customer-impact; relevant general awards. Optional tracks require actual implementation.

## Team
- Assume one builder until the user provides team context. No skill session should restart an unnecessary questionnaire.

## Problem
- Hypothesis: a coach reviewing submissions needs traceable evidence and specific gaps; public-school players without paid recruiting support may benefit.
- User/customer validation: pending. No coach endorsement or scholarship outcome is established.
- Distinct demo: source-linked observations, explicit uncertainty, and corrections that update a multi-clip profile.

## MVP journey
Upload short footage -> mark player/window -> inspect evidence -> correct/review -> see current multi-clip coverage -> request missing footage locally.
M0 is the first upload-to-evidence slice. M1 adds durable reviews/revisions. M2 completes the same journey. Exact gates are in docs/01_BUILD_PLAN.md.

## Cut list
Full-match analysis, automatic cross-match identity, player rankings, scholarship odds, scouting marketplace, outreach, payments, voice and unrelated sponsor APIs.

## Stack
Checked against hack-stack on 2026-10-25. The journey was already chosen; this pass did not reopen ideation.

- anthropics/anthropic-sdk-python: in the catalog. Calls Claude from the Python API. About 10 minutes, API key required, MIT. Install: `pip install anthropic`.
- Next.js/TypeScript: not in the catalog. Already chosen for the review UI. npm 16.4.3 exists. No key.
- FastAPI/Pydantic: not in the catalog. Already chosen. PyPI fastapi 0.162.0 exists. No key.
- FFmpeg/ffprobe 7.1: not in the catalog. Already installed. No key.
- SQLite via the Python stdlib: not in the catalog. Keeps the demo on one machine. The catalog's Supabase option needs an account, so it stays out.

Manual anchors first. SAM 2.1 and Jev stay off until the core loop works. No Redis, Celery, vector database, scraping, auth, or payments.

```text
browser review page -> FastAPI -> SQLite jobs
                    -> local MP4/frames
                    -> one Claude vision call
```

Riskiest assumption: a useful, correctly attributed observation from about two frames per second of a distant fullback. Spike that on a real clip before adding surface area.

## Honesty
- The coach hypothesis is unvalidated. No coach has used this, and no scholarship outcome is claimed.
- `fixtures/synthetic/` is generated colour, not football. `EVIDENCE_PROVIDER=synthetic` is opt-in. The 2026-10-25 browser walkthrough used it because no API key was set. The page showed "SYNTHETIC FIXTURE, not football analysis." A provider failure does not switch to it.
- The review clip is CC BY-SA 4.0 by Manchesterunited1234, kept local. `can_publish` is false. Attribution is required if it is shown. Adult status is "professional senior league per title, not individually verified."
- No Claude call has succeeded. Token and cost figures from the walkthrough ($0.0006, 100+40 tokens) are the synthetic ledger, not an Anthropic invoice.
- Prices in config are a snapshot of $2 / $10 per million tokens. No new paid infrastructure was started.

## Pitch
SecondLook helps coaches inspect the evidence behind submitted footage and identify what they still need to see. Roles assumed solo until assigned.

## Status log
- Planning kit prepared 2026-10-24. Next: verify clock/key/footage and build M0. No implementation acceptance gates have passed.
- 2026-10-25 ~00:00 UTC. hack-scope refine, no questionnaire. Deadline 16:00 UTC. About 16 hours were left at 23:50 UTC; reserve the last 90 minutes for submission and demo. Solo. One journey: upload a short clip, mark the fullback and a 6-8s window, read source-linked candidate observations or an honest gap. Judging check at scope time: application pass (a coach, at the moment of reviewing submitted footage); functionality fail until M0 runs; creativity pass (provenance and abstention, not a rating); technical complexity pass only if the timestamp and citation path is real. Cut list unchanged.
- 2026-10-25 ~00:00 UTC. hack-stack confirmed the stack above. Skills under .agents/skills match third_party/calhacks-kit/SHA256SUMS (12 files). Event preset in hack-scope/events is older; HACK.md and docs/08_SPONSORS_AND_COSTS.md win.
- 2026-10-25 00:37 UTC. hack-check, phase Build (about 15h 23m left). Weakest criterion: functionality, because the real model call has not run. Next action: add ANTHROPIC_API_KEY and repeat the 0–8 s fullback window on Claude. Anthropic track is not met until that call exists. No cut-list work was added.
