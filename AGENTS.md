# SecondLook

A coach reviews source-linked football observations, corrects attribution, and sees evidence coverage. Finish the committed journey before optional work.

Invariants:
- Validate source video time and frame references. An ability estimate is AI-written, labelled unverified, cites events, and is withheld below evidence confidence 40. Never invent statistics or scholarship probabilities.
- Every claim stays candidate until reviewed. Corrections create revisions and invalidate dependent claims.
- Missing evidence is not a weakness. Ambiguous identity means abstain or correct.
- No silent mock fallback. Label cached, replayed, manual, and synthetic material.
- Keep keys server-side. Cap upload size, calls, concurrency, and cost.
- Pydantic is the API contract. Preserve existing work and lock installed dependencies.
- Record verified commands and the next task in docs/STATE.md. Do not claim unrun tests passed.

Read one file in docs/ for the task. Skills are folders in skills/. Each SKILL.md starts with a one-line description. Open a skill only when that description matches the task.
