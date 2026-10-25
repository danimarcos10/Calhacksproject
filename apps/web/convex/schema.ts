import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

// Convex owns every mutable review field. The Python worker owns media, frames,
// execution jobs, the budget ledger and the result cache, and publishes immutable
// analysis records here. Append-only tables are marked; nothing patches them.

export const box = v.object({ x: v.number(), y: v.number(), w: v.number(), h: v.number() });

export const anchor = v.object({
  frameId: v.string(),
  state: v.union(v.literal("located"), v.literal("not_visible"), v.literal("uncertain")),
  source: v.optional(v.union(v.literal("manual"), v.literal("estimated"))),
  box: v.optional(box),
  method: v.optional(v.string()),
  reason: v.optional(v.string()),
  explicit: v.optional(v.boolean()),
});

export const spend = v.object({
  reconciledUsd: v.number(),
  liveCalls: v.number(),
  syntheticCalls: v.number(),
  unknownUsageAttempts: v.number(),
  failedJobs: v.number(),
  cachedReuses: v.number(),
});

export const requestStatus = v.union(
  v.literal("queued"),
  v.literal("running"),
  v.literal("succeeded"),
  v.literal("failed"),
  v.literal("outdated"),
);

export default defineSchema({
  players: defineTable({
    key: v.string(),
    displayName: v.string(),
    createdAt: v.number(),
  }).index("by_key", ["key"]),

  submissions: defineTable({
    key: v.string(),
    playerId: v.id("players"),
    title: v.string(),
    accessHash: v.string(),
    rightsNote: v.string(),
    createdAt: v.number(),
  }).index("by_key", ["key"]),

  windows: defineTable({
    submissionId: v.id("submissions"),
    order: v.number(),
    videoKey: v.string(),
    manifestKey: v.string(),
    videoDurationMs: v.number(),
    startMs: v.number(),
    endMs: v.number(),
    frames: v.array(v.object({ frameId: v.string(), tMs: v.number() })),
    link: v.object({ statement: v.string(), assertedBy: v.string(), assertedAt: v.number() }),
    currentRevision: v.number(),
    spend: v.optional(spend),
    kind: v.optional(v.union(v.literal("window"), v.literal("scout"))),
  })
    .index("by_submission", ["submissionId", "order"])
    .index("by_manifest", ["manifestKey"]),

  // Append-only. The window's currentRevision points at the newest one.
  revisions: defineTable({
    windowId: v.id("windows"),
    submissionId: v.id("submissions"),
    number: v.number(),
    key: v.string(),
    anchors: v.array(anchor),
    jerseyNote: v.string(),
    teamColorNote: v.string(),
    note: v.string(),
    origin: v.union(v.literal("imported"), v.literal("prepare"), v.literal("correction")),
    savedBy: v.string(),
    proposed: v.optional(v.object({ offered: v.number(), kept: v.number() })),
    createdAt: v.number(),
  })
    .index("by_window", ["windowId", "number"])
    .index("by_key", ["key"]),

  analysisRequests: defineTable({
    windowId: v.id("windows"),
    submissionId: v.id("submissions"),
    revisionId: v.id("revisions"),
    revisionNumber: v.number(),
    status: requestStatus,
    stage: v.optional(v.string()),
    attempt: v.number(),
    leaseUntil: v.optional(v.number()),
    workerId: v.optional(v.string()),
    jobKey: v.optional(v.string()),
    runId: v.optional(v.id("runs")),
    errorCode: v.optional(v.string()),
    errorMessage: v.optional(v.string()),
    retryable: v.optional(v.boolean()),
    requestedBy: v.string(),
    createdAt: v.number(),
    updatedAt: v.number(),
    kind: v.optional(v.union(v.literal("window"), v.literal("scout"))),
    cancelRequested: v.optional(v.boolean()),
    progress: v.optional(
      v.object({
        phase: v.string(),
        chunksDone: v.optional(v.number()),
        chunksTotal: v.optional(v.number()),
        candidates: v.optional(v.number()),
        inspected: v.optional(v.number()),
        trackedMs: v.optional(v.number()),
        lostMs: v.optional(v.number()),
        ballUnseenMs: v.optional(v.number()),
        spendUsd: v.optional(v.number()),
        message: v.optional(v.string()),
      }),
    ),
  })
    .index("by_status", ["status", "createdAt"])
    .index("by_window", ["windowId", "createdAt"])
    .index("by_submission", ["submissionId", "createdAt"]),

  // Written only by the worker. Immutable after insert.
  runs: defineTable({
    windowId: v.id("windows"),
    submissionId: v.id("submissions"),
    requestId: v.id("analysisRequests"),
    revisionNumber: v.number(),
    revisionKey: v.string(),
    key: v.string(),
    jobKey: v.string(),
    cacheStatus: v.string(),
    outdatedOnArrival: v.boolean(),
    model: v.string(),
    promptVersion: v.string(),
    schemaVersion: v.string(),
    providerLabel: v.string(),
    costUsd: v.union(v.number(), v.null()),
    inputTokens: v.union(v.number(), v.null()),
    outputTokens: v.union(v.number(), v.null()),
    latencyMs: v.union(v.number(), v.null()),
    gaps: v.array(v.string()),
    issues: v.array(v.string()),
    noObservationReason: v.union(v.string(), v.null()),
    createdAt: v.string(),
    publishedAt: v.number(),
    state: v.optional(v.union(v.literal("running"), v.literal("succeeded"), v.literal("partial"), v.literal("cancelled"))),
    coverageNote: v.optional(v.string()),
    narrative: v.optional(v.string()),
    trackedMs: v.optional(v.number()),
  })
    .index("by_window", ["windowId", "publishedAt"])
    .index("by_submission", ["submissionId", "publishedAt"])
    .index("by_window_key", ["windowId", "revisionNumber", "key"]),

  // Written only by the worker. Immutable after insert.
  observations: defineTable({
    runId: v.id("runs"),
    windowId: v.id("windows"),
    submissionId: v.id("submissions"),
    revisionNumber: v.number(),
    key: v.string(),
    category: v.string(),
    startMs: v.number(),
    endMs: v.number(),
    seekMs: v.number(),
    frameIds: v.array(v.string()),
    visibleAction: v.string(),
    outcome: v.string(),
    evidenceStatus: v.string(),
    identityStatus: v.string(),
    limitations: v.array(v.string()),
    attributionHold: v.boolean(),
    holdReason: v.union(v.string(), v.null()),
    holdFrameId: v.union(v.string(), v.null()),
    action: v.optional(v.string()),
    outcomeDetail: v.optional(v.string()),
  })
    .index("by_run", ["runId"])
    .index("by_submission", ["submissionId"]),

  // Append-only. The newest decision per observation is its review state.
  decisions: defineTable({
    submissionId: v.id("submissions"),
    observationId: v.id("observations"),
    runId: v.id("runs"),
    revisionNumber: v.number(),
    action: v.union(v.literal("accept"), v.literal("reject"), v.literal("reset")),
    reason: v.optional(v.string()),
    reviewer: v.string(),
    createdAt: v.number(),
  })
    .index("by_submission", ["submissionId", "createdAt"])
    .index("by_observation", ["observationId", "createdAt"]),

  // Append-only. The newest entry is the current note.
  notes: defineTable({
    submissionId: v.id("submissions"),
    body: v.string(),
    reviewer: v.string(),
    createdAt: v.number(),
  }).index("by_submission", ["submissionId", "createdAt"]),

  // Append-only. The newest entry is the current footage request.
  footageRequests: defineTable({
    submissionId: v.id("submissions"),
    body: v.string(),
    reviewer: v.string(),
    createdAt: v.number(),
  }).index("by_submission", ["submissionId", "createdAt"]),

  // Append-only. The newest profile for a submission is the current one.
  profiles: defineTable({
    submissionId: v.id("submissions"),
    key: v.string(),
    eventIds: v.array(v.string()),
    summary: v.string(),
    qualities: v.array(v.object({ text: v.string(), eventIds: v.array(v.string()) })),
    gaps: v.array(v.string()),
    ability: v.optional(
      v.object({
        overall: v.number(),
        dimensions: v.array(
          v.object({
            name: v.union(v.literal("ball_security"), v.literal("passing"), v.literal("carrying"), v.literal("involvement")),
            score: v.number(),
            reason: v.string(),
            eventIds: v.array(v.string()),
          }),
        ),
      }),
    ),
    model: v.string(),
    promptVersion: v.string(),
    costUsd: v.union(v.number(), v.null()),
    inputTokens: v.union(v.number(), v.null()),
    outputTokens: v.union(v.number(), v.null()),
    cacheStatus: v.string(),
    createdAt: v.number(),
  })
    .index("by_submission", ["submissionId", "createdAt"])
    .index("by_submission_key", ["submissionId", "key"]),

  // Written by the worker when a track is lost. The coach resolves it with a new revision.
  correctionRequests: defineTable({
    submissionId: v.id("submissions"),
    windowId: v.id("windows"),
    revisionNumber: v.number(),
    tMs: v.number(),
    frameId: v.string(),
    reason: v.string(),
    boxes: v.array(v.object({ trackId: v.optional(v.number()), box, confidence: v.number() })),
    createdAt: v.number(),
  }).index("by_window", ["windowId", "createdAt"]),
});
