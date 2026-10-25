# Data model: preserve observations and revisions

## Core entities
| Entity | Essential fields |
| --- | --- |
| Player | id, display_alias, stated_role, created_at |
| Submission | id, player_id, review_state, user_notes |
| Video | id, submission_id, sha256, path, duration_ms, metadata, rights_note |
| ClipContext | video_id, declared_match_id, source_date, selected interval |
| TargetRevision | id, video_id, revision, anchors_json, created_at |
| AnalysisRun | id, video_id, target_revision_id, input_hash, model, prompt/schema versions, status, usage |
| Observation | id, run_id, category, source interval, frame IDs, action, limitations, review_status |
| ReviewAction | id, observation_id, action, reason, created_at, reviewer_alias |
| Job | id, kind, input revision, stage, attempts, timestamps, error code |
| FootageRequest | id, player_id, category, reason, status, created_at |

Use generated UUIDs or equivalent opaque IDs. Store times in UTC and durations/positions in integer milliseconds. Persist the input manifest and raw provider response privately for debugging, with a retention/delete path. Avoid logging frames, keys, or private notes to third-party analytics.

## Statuses mean different things
Observation review_status is candidate, accepted, rejected or stale. Model evidence_status is observable, ambiguous or not_observable. Job status is queued, running, succeeded, failed, cancelled or interrupted. Do not collapse these into a single “confidence” field.

A coach can accept an observation about uncertainty: for example, the ball outcome is not visible. That should populate a gap or limitation, not a successful-action count. Reviewed positive evidence counts require an accepted, current, observable action.

## Revision rules
Changing player anchors creates a new TargetRevision, never an in-place historical overwrite. In one transaction, mark dependent observations stale and the current report outdated. Queue a new AnalysisRun referencing the new revision. Before committing worker output, verify the input revision is still current; stale workers cannot replace a newer result.

Review actions are append-only for this prototype. The latest applicable action determines current status, while the original model output remains inspectable. If a coach edits the text, store that as an attributed human note or edited revision; do not present it as the original model's output.

## Field ownership from M1
Each mutable field has one owner. Nothing below is copied into a second writable store.

| Data | Owner | Rule |
| --- | --- | --- |
| Player, submission, review code digest, rights note | Convex `players`, `submissions` | Created by the worker secret; read only with the submission's review code |
| Window, its frames, player link statement, current selection number | Convex `windows` | `currentRevision` moves forward only through `saveRevision` |
| Player selection (anchors, notes, origin, proposals offered and kept) | Convex `revisions`, append-only | Saving on top of an older number is refused; estimated boxes stay estimated unless confirmed |
| Analysis request (queued, running, succeeded, failed, outdated; stage, attempt, lease) | Convex `analysisRequests` | One open request per window and selection |
| Run and observations | Convex `runs`, `observations`, written only by the worker | Immutable; published once per window, selection and run key |
| Decisions | Convex `decisions`, append-only | Tied to observation and selection number; refused on stale or held moments |
| Coach note, next-footage request | Convex `notes`, `footageRequests`, append-only | Newest wins; history kept |
| Video, manifest, frames, sampled media | SQLite and `DATA_DIR` | API only |
| Execution job, budget ledger, result cache | SQLite | Worker only; budget rows are reserve, reconcile or release |
| Worker copy of a selection | SQLite `target_revisions` | Immutable, keyed by the Convex `rev_` key; not edited by any UI |

Moment status is derived, not stored. It is stale when its run is not the current one for the window's selection, held under an identity hold, and otherwise follows the newest decision. A reset counts as an AI suggestion.

## Match identity and duplication
A declared match ID is user-supplied context. Do not infer distinct matches from file count. Exact duplicate hashes can be detected; overlapping or re-encoded highlights may still duplicate an event. Offer a “same incident” grouping and prevent those records from inflating coverage.

---

# A concrete observation contract

The following is an illustrative wire contract, not a real analyzed player. Labels and numbers exist to show types and invariants. The server assigns stable observation IDs after validating the provider's response.

```json
{
  "schema_version": "1.0",
  "video_id": "vid_example",
  "target_revision": 2,
  "window": {"start_ms": 20000, "end_ms": 28000},
  "observations": [{
    "category": "passing_action",
    "start_ms": 23000,
    "end_ms": 25000,
    "frame_ids": ["frame_23000", "frame_24500"],
    "visible_action": "Target plays the ball toward a teammate.",
    "outcome": "not_observable",
    "evidence_status": "ambiguous",
    "identity_status": "clear_in_cited_frames",
    "limitations": ["Recipient is off-screen at the end."]
  }],
  "gaps": ["Pass completion is not visible."],
  "resample_request": null
}
```

## Pydantic implementation requirements
Use enums for category, outcome, evidence_status and identity_status. Set extra fields to forbid. Validate start_ms < end_ms and containment within the actual selected window. Limit observations to five per call and keep action text concise. Limit frame references to known IDs. A resample request must include a narrow range and one specific visibility reason.

Keep provider-facing schema fields separate from trusted server fields: run_id, observation_id, review_status, source hashes, timestamps and token usage come from application logic. Never let the model choose an accepted review status or claim that a coach has approved something.

## Semantic rejection examples
- A cited frame ID was never sent: discard the observation and log a validation issue.
- A “completed pass” has outcome not_observable: downgrade to a visible passing action with an unresolved outcome, or reject the inconsistent output.
- Time is outside the sampled window: reject rather than silently clamping the claim into another moment.
- Identity is ambiguous: do not count the action as this player's evidence. Request a correction or preserve it only as an unresolved candidate.
- A report says “excellent football IQ”: remove unsupported trait language; keep only a concrete, attributable observation.

Structured output makes data easier to parse. It does not prove that the action happened. The application needs both schema validation and domain checks, followed by human review. [S10]

---

# HTTP endpoints and durable jobs

| Method / route | Purpose and response |
| --- | --- |
| POST /api/videos | Multipart ingest; returns video ID and metadata |
| GET /api/videos/{id}/media | Browser-playable media with byte-range support |
| POST /api/videos/{id}/samples | Bounded interval; returns manifest and frame URLs |
| POST /api/videos/{id}/targets | Save normalized anchors; return new revision |
| POST /api/analyses | Validate input, deduplicate, enqueue; return job ID |
| GET /api/jobs/{id} | Real stage, status, error, result ID, timings |
| GET /api/analyses/{id} | Current or historic observations and provenance |
| POST /api/observations/{id}/reviews | Accept/reject with reason; append review action |
| GET /api/players/{id}/profile | Deterministic current evidence rollup |
| GET /api/submissions | Coach inbox with review status and coverage |
| POST /api/players/{id}/requests | Create an in-app request for more footage |
| DELETE /api/videos/{id} | Remove clip and derived artifacts; invalidate rollups |

Correction flow uses the targets endpoint, then a fresh analyses request. Compare views can read two existing profiles; a new comparison service is unnecessary. Use one consistent JSON error envelope: code, user_message, retryable and request_id. Never return provider secrets or internal absolute paths.

## Worker rules
Claim a queued job atomically in a short SQLite transaction. Run one worker initially, with a heartbeat or started_at lease. On restart, mark interrupted work clearly; retry only bounded, idempotent steps. Write files to a temporary name and rename after success. Do not leave half-written JSON looking complete.

Fingerprint inputs using video hash, interval, anchor revision, sampler version, model ID, prompt version and schema version. Reuse a matching successful result and show it as cached. Changing identity, prompt or model invalidates that cache. Use an idempotency key to prevent a double click from creating duplicate paid work.

## Polling and failure behavior
Poll roughly once per second while active, then stop at a terminal state. Label stages honestly; use an indeterminate indicator when no reliable percentage exists. Configure provider timeouts and at most two retries for transient errors, respecting Retry-After. Retries count toward job and session budgets.

Set a proposed 120-second overall job deadline for the short demo input and tune it after measurement. An overdue job yields a visible timeout with retry or smaller-window options. Cancellation prevents later stages and stale commits; it may not cancel already-billed provider work.
