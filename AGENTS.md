# SecondLook project instructions

Read HACK.md and docs/STATE.md at the start of a session. Then read only the document needed for the current task. The full PDF in reference/ is a human/deep-reference artifact; do not repeatedly ingest it.

Goal: a coach reviews source-linked football observations, corrects attribution, and sees current evidence coverage. Ship the real M0 loop first, then follow the committed milestones.

Invariants:
- Source video time and frame references must be validated. An ability estimate is AI-written, labelled unverified, cites events, and is withheld below evidence confidence 40. Never invent statistics or scholarship probabilities.
- Every claim remains candidate until reviewed. Corrections create revisions and invalidate dependent claims.
- Missing evidence is not a player's weakness. Ambiguous identity requires abstention or correction.
- No silent mock fallback. Label cached, replayed, manual and synthetic material.
- Keep keys server-side. Cap upload size, calls, concurrency and costs. Do not add providers for logos.
- Use Pydantic as the API contract source. Preserve existing work and lock installed dependencies.
- Update STATE.md with verified commands/behavior and next task, under 300 words. Do not claim unrun tests passed.

Document index:
- Scope/timeline: docs/01_BUILD_PLAN.md
- Structure/config: docs/02_ARCHITECTURE.md
- Video/identity: docs/03_VIDEO_PIPELINE.md
- Schemas/API/revisions: docs/04_CONTRACTS.md
- Models/prompts/Jev: docs/05_AI_AND_PROMPTS.md
- UI/profiles: docs/06_PRODUCT_AND_UX.md
- Tests/feedback: docs/07_VALIDATION.md
- Credits/tracks: docs/08_SPONSORS_AND_COSTS.md
- Shipping/demo: docs/09_SHIP_AND_DEMO.md
- Next prompts: docs/10_CURSOR_PROMPTS.md
- Sources: docs/12_SOURCES.md

Mentor skills are in .agents/skills/. Load only the relevant skill. Current organizer/sponsor evidence overrides the older event preset. Finish the committed journey before optional integrations; shrink it if the deadline requires.
