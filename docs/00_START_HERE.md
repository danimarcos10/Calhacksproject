# The build decision

Build SecondLook: a football recruiting evidence workspace. A coach opens a player submission, sees specific observations tied to video, corrects a mistaken identification, and gets an updated assessment of what the footage does and does not show.

The first version should be crude and working within 90 minutes. That is the right approach here: the riskiest question is whether the footage supports useful observations, not whether a polished dashboard can be built. Show that first version to a mentor immediately.

The 15-hour ambition is one complete, convincing journey: upload two or three short clips for one player; mark the player; extract reviewable evidence; correct or reject a claim; see the profile update; compare evidence coverage with another submission; decide what footage to request next. Automatic tracking is a valuable upgrade if it works early. It is not the only route to a strong demo.

## Four commitments
- Ship a real model call against real, permissioned football footage before investing in design.
- Every football claim links to a source interval and has an explicit review state. Missing evidence remains missing.
- Spend the engineering effort on identity, timestamps, uncertainty, corrections, and cross-clip consistency.
- Use one primary model provider. Add sponsor technology only when it improves a visible part of this journey.

## Recommended stack
Next.js + TypeScript for the UI; FastAPI + Pydantic for contracts and orchestration; FFmpeg for media; SQLite and local files for the first deployment; Claude Sonnet for visual evidence extraction. Keep SAM 2.1 and Jev behind optional adapters.

## The claim to make
SecondLook helps coaches review submitted footage with traceable evidence and identify what they still need to see. College recruiting is a promising customer hypothesis, not a validated distribution channel. This prototype does not predict scholarships, rank human potential, or replace a coach's judgment.

## What this package contains
The PDF is the complete reference. The kit contains the same plan split into small Markdown files, a project context index, the initial Cursor prompt, milestone prompts, and George Kalangi's six original hackathon skills with their supporting files and MIT license. It is a build specification, not an already implemented or benchmarked product.

---

# The clock and the route through this manual

## Use the real submission deadline
Devpost and the supplied Hacker Guide agree: Sunday, October 25, 2026 at 09:00 PDT, which is 16:00 UTC and 17:00 CET in Madrid that day. Research clock: October 24 at approximately 22:48 UTC / 15:48 PDT; about 17 hours remained then. Recompute when you start. Do not assume there are still 15 usable hours. [S01, S02]

A 15-hour run starting at that research clock finishes around 06:48 PDT, leaving roughly two hours for submission failures and rest. The final three hours of the run already include hardening and presentation. Have a draft Devpost entry before the final hour; the guide recommends Saturday night. Being in person during judging is required by the guide.

## First actions: 15 minutes, maximum
1. Open the extracted kit folder in Cursor. Paste CURSOR_START_PROMPT.md. It tells Cursor to establish the project and build only M0 first.
2. Obtain one permissioned, clear, 30-90 second clip with a visible target player. Choose a 6-8 second incident within it. No footage was supplied with this package.
3. Claim the event Claude API credit and confirm access in the console. Approval can take time; the sponsor thread contains approval issues. Do not wait idle: build upload, selection, and validation meanwhile. [S04]
4. Set the actual deadline and team ownership in HACK.md. If working alone, use the solo plan in this manual. A teammate should own a whole boundary, not edit the same files simultaneously.

## Reading map for Cursor
| Task | Read only these files |
| --- | --- |
| Start or resume | AGENTS.md, HACK.md, docs/STATE.md |
| Choose next ticket | docs/01_BUILD_PLAN.md |
| Media or tracking | docs/03_VIDEO_PIPELINE.md |
| Backend / schemas | docs/02_ARCHITECTURE.md, docs/04_CONTRACTS.md |
| Model / Jev | docs/05_AI_AND_PROMPTS.md |
| Interface / profiles | docs/06_PRODUCT_AND_UX.md |
| Reliability / evaluation | docs/07_VALIDATION.md |
| Sponsors / budgets | docs/08_SPONSORS_AND_COSTS.md |
| Shipping / pitch | docs/09_SHIP_AND_DEMO.md |

The full PDF is for human reading and occasional deep reference. Files still consume tokens when the agent reads them. Small, selectively loaded Markdown files reduce repeated context; a PDF does not make context free.
