# A small evaluation that judges can inspect

## Build an evidence audit, not a benchmark claim
Use three to five permissioned clips and roughly 15-20 short windows if time allows. Include a clear action, an obscured ball, two same-color players crossing, a camera cut, a target leaving frame, and a duplicate incident. Keep at least one clip out of prompt tuning. If you have fewer examples, report the actual count.

Ask a coach or football-literate reviewer to mark whether each candidate observation is attributable to the selected player and supported by the cited interval. Record disagreement. Do not treat the model's own confidence or a second model's agreement as ground truth.

| Measure | Definition | What to report |
| --- | --- | --- |
| Grounded claim precision | Human-supported candidate claims / all candidate claims reviewed | Numerator, denominator and examples of failures |
| Identity errors | Claims assigned to the wrong player | Raw count; inspect every observed case |
| Useful abstention | Ambiguous windows correctly left unresolved | Count and representative cases |
| Evidence seeking | Links open the intended source interval | Tested links / total links |
| Correction integrity | Stale claims disappear from current rollups | Pass/fail on correction scenarios |
| Latency | Upload complete to usable report | Median and slowest run; hardware and input size |
| Cost | Actual provider usage per run | Observed dollars, tokens and retries |
| Review usefulness | Same review task with and without the tool | Small-session timings and qualitative comments |

Missing an event is a recall error, but you cannot estimate event recall without an annotated set of all relevant events. Do not claim comprehensive scouting accuracy from a precision-only audit. Do not extrapolate five clips to all players, camera types or universities.

## Meaningful implementation tests
Prioritize coordinate round trips after resize/rotation; timestamp mapping on variable-frame-rate footage; rejection of invented frame IDs and out-of-range intervals; idempotent double submissions; stale-worker output after a correction; duplicate-window coverage; and deletion of a source clip from derived rollups.

Use synthetic fixtures for deterministic plumbing tests and real footage for the end-to-end evidence audit. Keep those purposes distinct. Unit fixtures must never appear as live football analysis in the demo.

## Release gate
Every demo evidence link must work. No known wrong-player claim may remain accepted. Every intentional failure must be visible. The correction scenario must update the report after refresh. Accuracy, speed and time-saved claims in the pitch must come from recorded measurements, not the targets in this plan.

---

# Failure modes and cheap recovery paths

| Failure | Detection | Recovery |
| --- | --- | --- |
| Unsupported/huge video | ffprobe + size/resolution/duration caps | Explain limits; ask for a shorter export |
| Player too small | Preview inspection; unresolved identity | Request closer footage or manual anchors |
| Occlusion / shot cut | Target disappears, scene discontinuity | End the track; re-anchor next visible segment |
| Fast ball event between samples | Outcome not visible | One bounded denser resample, then abstain |
| Provider 401/403 | Authentication error | Preserve upload; show key/access setup problem |
| Provider 429/5xx | Typed transient error | Bounded retry with backoff, then visible failure |
| Malformed/unsupported response | Schema and semantic validation | Reject unsupported claims; never fabricate replacements |
| Worker dies | Lease/heartbeat expires | Mark interrupted; bounded idempotent resume |
| New correction during old run | Target revision mismatch | Discard old commit; retain it only as history |
| Budget exhausted | Reservation + usage ledger | Stop paid work; offer existing results/manual review |
| Network down at judging | Health check / failed live run | Open clearly labeled recorded result/video |
| Disk fills | Free-space guard | Stop new uploads; offer deletion; preserve current results |

## Cost and concurrency are reliability controls
Allow one active decode and one active analysis per worker initially. Reserve an estimated amount before provider calls and reconcile actual usage afterward. Count failed or retried calls if the provider bills them. A double-click must not charge twice. A refresh must not recreate the job.

## Make errors useful
Return a short message the user can act on: “The target leaves the frame after 00:06; choose a shorter interval or add a new anchor.” Keep technical details in a local run log with a request ID. Do not expose raw stack traces, provider keys or personal file paths in the UI.

## Reproducibility
For each real run, retain the input video hash, frame manifest, selected anchors, prompt/schema/model versions, provider usage, latency and resulting review history. This is enough to explain the demo and debug regressions. It does not require a separate experiment-tracking platform.

## What to avoid
No silent exception-to-success conversion; no fake percent progress; no endless polling; no hidden switching to a seeded report; no background process that can write after its input revision has changed. A candid failed run with a retry control is better product behavior than a convincing but unsupported result.

---

# Use mentors to test the assumption, not just the UI

## The first mentor visit
Bring the rough working loop, one clear clip and one uncertain clip. Introduce the proposed user in one sentence. Let the mentor try to find the evidence for an observation without you explaining each click. Capture what they do, not just whether they say the idea is good.

Ask: Which part would a coach distrust? Is the useful job initial triage, preparing an athlete's evidence packet, or reviewing a shortlist? What minimum footage would make this useful? Which current task would this replace or shorten? Who could give us one real workflow example today?

If the mentor lacks recruiting experience, treat their response as product/engineering feedback, not validation of a college buyer. A single real coach conversation can be more valuable than another integration. Do not invent a quote or claim a partnership from a casual conversation.

## The six-hour check
Show the correction loop and a profile built from two clips. Ask the reviewer to approve or reject three observations and request missing footage. Time that small task. Compare with the same task using raw video and notes, being explicit about order effects and the tiny sample. Record whether the tool saved navigation effort and whether it created new confusion.

## Keep a short validation record
| Field | Example of the kind of entry to make |
| --- | --- |
| Person / role | Coach, player, mentor; alias if preferred |
| Date and context | Five-minute demo at venue |
| Observed task | Find evidence for a passing action |
| Direct feedback | Accurate short quote, only if permitted |
| Interpretation | Our hypothesis about what it means |
| Change | Concrete UI or scope decision |
| Open question | What still has not been validated |

## Sponsor-specific questions worth asking
Anthropic: does the named community and demonstrated benefit meet the public-benefit intent, and what impact evidence would help? Microsoft: does the running bounded evidence agent meet the challenge, and is any additional platform requirement applicable? Meta, only if pursuing it: is the coach-player feedback loop a strong enough human-connection use case? Elastic, only if already adopted: verify Serverless Agent Builder and submission requirements.

Use the event mentor queue or visit the relevant table. This package does not send messages, book meetings or claim anyone's endorsement. The desired output is one validated workflow change and one concrete piece of user evidence.
