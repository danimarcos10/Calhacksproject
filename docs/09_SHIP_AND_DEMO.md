# Deployment, access, and footage handling

## Default deployment path
Run locally first. By M1, provide one documented command sequence for the web app, API and worker, with a shared DATA_DIR. If Docker is already familiar and installed, package the API/worker from one image and mount a durable volume on one machine. Do not spend the first hours learning container orchestration.

For a hosted demo, use an existing VM or container host with persistent disk, HTTPS and private server-side secrets. Keep the worker separate from request timeouts. A static frontend host alone cannot run FFmpeg jobs, persist SQLite reliably, or make a laptop-only API available to judges.

If Azure access is already approved, a private storage adapter and a suitable host can use the student credit. Verify service eligibility, region, quota and actual pricing in the account before provision. The $100 offer does not guarantee a GPU, quota approval or access to every marketplace product. [S15]

## Public access needs a smaller boundary
The early no-login build is appropriate for a local, single-operator demo with permissioned examples. Before exposing uploads publicly, add at least a server-checked demo access gate, rate limits, storage caps and authorization on media/result IDs. Unguessable IDs alone are not access control. If time is short, host only permissioned read-only demo results and keep live uploads local.

## Data handling that belongs in this product
Use footage you have permission to process and show. Record its source and permitted use. Prefer adult volunteers for the hackathon demonstration to simplify consent. If using minors' footage, obtain the required permission through the responsible adults/organization before upload or sharing. Do not assume publicly accessible sports footage is licensed for redistribution.

Show what will be sent to the model provider: selected frames and relevant notes. Avoid unnecessary names, dates of birth, school records, contact details or health information. Athlete aliases are sufficient for the demo. Keep media private and provide a delete action that removes frames, crops, responses and derived report references.

## Operational checks
Do not concatenate user filenames into shell commands. Generate internal paths and reject path traversal. Limit upload size at both proxy and API. Serve only files registered to the requested resource. Test byte-range seeking from the actual demo browser. Avoid public debug endpoints. Keep the original media immutable and clean up failed temporary files.

After a successful event demo, turn off unused compute and revoke temporary public access. Persistent hosting is a later product decision, not a reason to keep a GPU running unnoticed.

---

# The two-minute demo

Use this as a script skeleton, replacing placeholders only with things the working build proves. Prepare a two-minute core and a longer version if judges allow it. The exact judging slot should be checked onsite; the supplied material and event listings are not perfectly uniform.

## 00:00-00:15: the job
“A coach reviewing submitted football footage needs to know which moments support a claim and what is still missing. SecondLook turns short submissions into a reviewable evidence packet. Our first target users are [the specific group actually validated].”

## 00:15-00:45: open the evidence
Open a real submission. Play a short source interval. Select an observation and show that it seeks the exact moment. “This is a suggested observation with its evidence and its limits. We distinguish an action we can see from an outcome the footage does not show.”

## 00:45-01:15: correct the system
Open the chosen correction scenario. “Here the target becomes ambiguous. A coach can correct the player selection.” Save the anchor, show the old claim becoming stale, then show the actual refreshed result or a clearly labeled previously recorded rerun if latency requires it. Explain that the profile no longer counts the disputed evidence.

## 01:15-01:40: demonstrate the final workflow
Open the multi-clip profile and comparison. Show coverage, distinct submitted matches, and an unresolved category. Create an in-app request for more footage. “The output is a concrete next review step, not a scholarship prediction.”

## 01:40-02:00: explain the hard part and impact
“We built timestamp-preserving video processing, explicit target revisions, schema-checked visual extraction and evidence invalidation. On [actual number] reviewed examples, we observed [actual result]. Our next test is [real next validation step].”

## Disclosure line
State exactly what is live, cached, manually anchored or recorded. If the two-minute flow opens precomputed analysis for speed, say so and show the live upload path separately. Do not hide manual selections or describe a recorded result as real-time processing.

## Thirty-second version
“SecondLook helps a coach inspect the evidence behind a player's submitted footage. Every observation opens its source moment. If the player was tracked incorrectly, correcting it updates the assessment and shows what remains unknown. We are measuring whether that makes review faster and more useful.”

Record a 60-90 second backup of the real running product. Keep it available locally, alongside the sample video and cached result. Rehearse the entire sequence three times, including opening the backup when the network fails.

---

# Submission and likely judge questions

## Before the deadline
Run hack-ship from the bundled skills. Verify the README from a clean directory; scan current files and history for secrets without printing secret values; open links as a logged-out viewer; add every teammate; upload the project image and demo; select only qualifying tracks; and complete any sponsor-specific extra steps. Submit early enough to recover from a failed video upload. [S01, S02, S07]

The supplied guide says projects must be submitted by Sunday 09:00 PDT, participants must be present for judging, and teams should reach their assigned tables by 10:30. Recheck announcements for changes. Do not confuse the end of hacking or closing ceremony with the submission deadline.

## README contents
One-line value proposition; real demo link; target user and evidence of need; architecture; setup and required environment variables; how to supply permissioned footage; exact test/run commands; measured results; known limits; what is cached/manual/synthetic; and attribution for AI coding tools and open-source components, including the mentor kit.

## Judge answers to prepare
| Question | Honest, concrete answer shape |
| --- | --- |
| Why would a coach use this? | Describe one observed review task and feedback; name what remains unvalidated. |
| Isn't this already available? | Existing platforms offer profiles/clips/AI features; show your evidence/correction workflow and avoid broad novelty claims. |
| How accurate is it? | Give the actual audit size and grounded-claim results; distinguish precision from event recall. |
| What did you build? | Media/time mapping, target/revision workflow, validation, persistence, aggregation and UI; credit the models/libraries. |
| Why not just ask a video model? | A useful product also needs identity, source citations, correction semantics, state and workflow. |
| What breaks at 1,000 users? | Single worker and local storage; next steps are queueing, private object storage, database migration and access controls. |
| Why Claude / Jev? | Claude handles visual evidence; Jev is optional text routing if actually implemented. Never claim unused providers. |
| Can it award scholarships? | No. It supports evidence review; coaches and institutions make decisions under their own processes. |

Do not show target performance numbers as achieved metrics. Do not call a tiny evaluation a validated scouting model. If asked about commercialization, explain the next customer interview and pilot test, not a fabricated revenue projection.

Slides are optional. If needed after the product works, run hack-pitch then hack-showtime using screenshots of the real app. The bundled slide template is not a reason to spend the final build hours making a deck.
