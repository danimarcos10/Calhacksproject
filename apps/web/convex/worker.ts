import { ConvexError, v } from "convex/values";
import { mutation } from "./_generated/server";
import type { Doc, Id } from "./_generated/dataModel";
import type { MutationCtx } from "./_generated/server";
import { requireWorker } from "./lib/access";
import { currentRuns } from "./lib/status";
import { anchor, box, spend } from "./schema";

// Every function here is called by the local Python worker over an outbound
// connection and requires the worker secret. Browsers never call these.

const LEASE_MS = 10 * 60 * 1000;

export const createSubmission = mutation({
  args: {
    secret: v.string(),
    key: v.string(),
    playerKey: v.string(),
    playerName: v.string(),
    title: v.string(),
    accessHash: v.string(),
    rightsNote: v.string(),
  },
  handler: async (ctx, args) => {
    await requireWorker(args.secret);
    const existing = await ctx.db
      .query("submissions")
      .withIndex("by_key", (q) => q.eq("key", args.key))
      .unique();
    if (existing) return existing._id;
    const player = await ctx.db
      .query("players")
      .withIndex("by_key", (q) => q.eq("key", args.playerKey))
      .unique();
    const now = Date.now();
    const playerId =
      player?._id ?? (await ctx.db.insert("players", { key: args.playerKey, displayName: args.playerName, createdAt: now }));
    return await ctx.db.insert("submissions", {
      key: args.key,
      playerId,
      title: args.title,
      accessHash: args.accessHash,
      rightsNote: args.rightsNote,
      createdAt: now,
    });
  },
});

export const registerWindow = mutation({
  args: {
    secret: v.string(),
    submissionKey: v.string(),
    order: v.number(),
    videoKey: v.string(),
    manifestKey: v.string(),
    videoDurationMs: v.number(),
    startMs: v.number(),
    endMs: v.number(),
    frames: v.array(v.object({ frameId: v.string(), tMs: v.number() })),
    linkStatement: v.string(),
    assertedBy: v.string(),
    kind: v.optional(v.union(v.literal("window"), v.literal("scout"))),
    initialRevision: v.optional(
      v.object({
        key: v.string(),
        anchors: v.array(anchor),
        jerseyNote: v.string(),
        teamColorNote: v.string(),
        note: v.string(),
      }),
    ),
  },
  handler: async (ctx, args) => {
    await requireWorker(args.secret);
    if (!args.linkStatement.trim()) {
      throw new ConvexError({ code: "link_required", message: "Linking a clip to a player needs an explicit statement." });
    }
    const submission = await ctx.db
      .query("submissions")
      .withIndex("by_key", (q) => q.eq("key", args.submissionKey))
      .unique();
    if (!submission) throw new ConvexError({ code: "not_found", message: "Unknown submission." });
    const existing = await ctx.db
      .query("windows")
      .withIndex("by_manifest", (q) => q.eq("manifestKey", args.manifestKey))
      .unique();
    if (existing) {
      if (existing.submissionId !== submission._id) {
        throw new ConvexError({ code: "window_taken", message: "This window already belongs to another submission." });
      }
      return existing._id;
    }
    const now = Date.now();
    const windowId = await ctx.db.insert("windows", {
      submissionId: submission._id,
      order: args.order,
      videoKey: args.videoKey,
      manifestKey: args.manifestKey,
      videoDurationMs: args.videoDurationMs,
      startMs: args.startMs,
      endMs: args.endMs,
      frames: args.frames,
      link: { statement: args.linkStatement.trim(), assertedBy: args.assertedBy, assertedAt: now },
      currentRevision: args.initialRevision ? 1 : 0,
      ...(args.kind ? { kind: args.kind } : {}),
    });
    if (args.initialRevision) {
      await ctx.db.insert("revisions", {
        windowId,
        submissionId: submission._id,
        number: 1,
        key: args.initialRevision.key,
        anchors: args.initialRevision.anchors,
        jerseyNote: args.initialRevision.jerseyNote,
        teamColorNote: args.initialRevision.teamColorNote,
        note: args.initialRevision.note,
        origin: "imported",
        savedBy: args.assertedBy,
        createdAt: now,
      });
    }
    return windowId;
  },
});

async function markOutdated(ctx: MutationCtx, request: Doc<"analysisRequests">, now: number) {
  await ctx.db.patch(request._id, {
    status: "outdated",
    errorCode: "outdated_revision",
    errorMessage: "The player selection changed before this analysis started.",
    leaseUntil: undefined,
    updatedAt: now,
  });
}

export const claimNext = mutation({
  args: { secret: v.string(), workerId: v.string() },
  handler: async (ctx, { secret, workerId }) => {
    await requireWorker(secret);
    const now = Date.now();
    const queued = await ctx.db
      .query("analysisRequests")
      .withIndex("by_status", (q) => q.eq("status", "queued"))
      .order("asc")
      .take(20);
    const running = await ctx.db
      .query("analysisRequests")
      .withIndex("by_status", (q) => q.eq("status", "running"))
      .order("asc")
      .take(20);
    const candidates = [...running.filter((item) => (item.leaseUntil ?? 0) < now), ...queued];
    for (const request of candidates) {
      const window = await ctx.db.get(request.windowId);
      if (!window || window.currentRevision !== request.revisionNumber) {
        await markOutdated(ctx, request, now);
        continue;
      }
      const revision = await ctx.db.get(request.revisionId);
      if (!revision) {
        await markOutdated(ctx, request, now);
        continue;
      }
      const attempt = request.attempt + 1;
      await ctx.db.patch(request._id, {
        status: "running",
        stage: "claimed",
        attempt,
        workerId,
        leaseUntil: now + LEASE_MS,
        updatedAt: now,
      });
      return {
        requestId: request._id,
        attempt,
        kind: request.kind ?? window.kind ?? "window",
        window: {
          videoKey: window.videoKey,
          manifestKey: window.manifestKey,
          startMs: window.startMs,
          endMs: window.endMs,
          videoDurationMs: window.videoDurationMs,
          frames: window.frames,
        },
        revision: {
          key: revision.key,
          number: revision.number,
          anchors: revision.anchors,
          jerseyNote: revision.jerseyNote,
          teamColorNote: revision.teamColorNote,
          note: revision.note,
        },
      };
    }
    return null;
  },
});

export const progress = mutation({
  args: {
    secret: v.string(),
    requestId: v.id("analysisRequests"),
    stage: v.string(),
    jobKey: v.string(),
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
  },
  handler: async (ctx, { secret, requestId, stage, jobKey, progress: report }) => {
    await requireWorker(secret);
    const request = await ctx.db.get(requestId);
    if (!request || request.status !== "running") return { cancelRequested: false };
    const now = Date.now();
    await ctx.db.patch(requestId, {
      stage,
      jobKey,
      leaseUntil: now + LEASE_MS,
      updatedAt: now,
      ...(report ? { progress: report } : {}),
    });
    return { cancelRequested: request.cancelRequested === true };
  },
});

const publishedObservation = v.object({
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
});

const publishedRun = v.object({
  key: v.string(),
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
});

export const publishResult = mutation({
  args: {
    secret: v.string(),
    requestId: v.id("analysisRequests"),
    jobKey: v.string(),
    cacheStatus: v.string(),
    run: publishedRun,
    observations: v.array(publishedObservation),
  },
  handler: async (ctx, args) => {
    await requireWorker(args.secret);
    const request = await ctx.db.get(args.requestId);
    if (!request) throw new ConvexError({ code: "not_found", message: "Unknown analysis request." });
    const window = await ctx.db.get(request.windowId);
    const revision = await ctx.db.get(request.revisionId);
    if (!window || !revision) throw new ConvexError({ code: "not_found", message: "Window or revision missing." });
    const now = Date.now();

    let runId: Id<"runs">;
    const already = await ctx.db
      .query("runs")
      .withIndex("by_window_key", (q) =>
        q.eq("windowId", window._id).eq("revisionNumber", request.revisionNumber).eq("key", args.run.key),
      )
      .first();
    const outdated = window.currentRevision !== request.revisionNumber;
    if (already) {
      runId = already._id;
    } else {
      runId = await ctx.db.insert("runs", {
        ...args.run,
        windowId: window._id,
        submissionId: window.submissionId,
        requestId: request._id,
        revisionNumber: request.revisionNumber,
        revisionKey: revision.key,
        jobKey: args.jobKey,
        cacheStatus: args.cacheStatus,
        outdatedOnArrival: outdated,
        publishedAt: now,
      });
      for (const observation of args.observations) {
        await ctx.db.insert("observations", {
          ...observation,
          runId,
          windowId: window._id,
          submissionId: window.submissionId,
          revisionNumber: request.revisionNumber,
        });
      }
    }
    await ctx.db.patch(request._id, {
      status: outdated ? "outdated" : "succeeded",
      stage: "published",
      runId,
      jobKey: args.jobKey,
      leaseUntil: undefined,
      errorCode: outdated ? "outdated_revision" : undefined,
      errorMessage: outdated ? "The player selection changed while this analysis ran. Its result is kept in history only." : undefined,
      updatedAt: now,
    });
    return { runId, outdated };
  },
});

export const failRequest = mutation({
  args: {
    secret: v.string(),
    requestId: v.id("analysisRequests"),
    jobKey: v.optional(v.string()),
    errorCode: v.string(),
    errorMessage: v.string(),
    retryable: v.boolean(),
  },
  handler: async (ctx, args) => {
    await requireWorker(args.secret);
    const request = await ctx.db.get(args.requestId);
    if (!request || request.status === "succeeded" || request.status === "outdated") return false;
    await ctx.db.patch(request._id, {
      status: "failed",
      jobKey: args.jobKey ?? request.jobKey,
      errorCode: args.errorCode,
      errorMessage: args.errorMessage,
      retryable: args.retryable,
      leaseUntil: undefined,
      updatedAt: Date.now(),
    });
    return true;
  },
});

export const setWindowCost = mutation({
  args: { secret: v.string(), manifestKey: v.string(), ...spend.fields },
  handler: async (ctx, { secret, manifestKey, ...rest }) => {
    await requireWorker(secret);
    const window = await ctx.db
      .query("windows")
      .withIndex("by_manifest", (q) => q.eq("manifestKey", manifestKey))
      .unique();
    if (!window) return false;
    await ctx.db.patch(window._id, { spend: rest });
    return true;
  },
});

const scoutObservation = v.object({
  key: v.string(),
  category: v.string(),
  action: v.string(),
  outcomeDetail: v.string(),
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
});

export const openRun = mutation({
  args: {
    secret: v.string(),
    requestId: v.id("analysisRequests"),
    runKey: v.string(),
    model: v.string(),
    promptVersion: v.string(),
    schemaVersion: v.string(),
  },
  handler: async (ctx, args) => {
    await requireWorker(args.secret);
    const request = await ctx.db.get(args.requestId);
    if (!request) throw new ConvexError({ code: "not_found", message: "Unknown analysis request." });
    const window = await ctx.db.get(request.windowId);
    const revision = await ctx.db.get(request.revisionId);
    if (!window || !revision) throw new ConvexError({ code: "not_found", message: "Window or revision missing." });
    const existing = await ctx.db
      .query("runs")
      .withIndex("by_window_key", (q) =>
        q.eq("windowId", window._id).eq("revisionNumber", request.revisionNumber).eq("key", args.runKey),
      )
      .first();
    if (existing) {
      await ctx.db.patch(existing._id, { state: "running" });
      return existing._id;
    }
    const now = Date.now();
    return await ctx.db.insert("runs", {
      windowId: window._id,
      submissionId: window.submissionId,
      requestId: request._id,
      revisionNumber: request.revisionNumber,
      revisionKey: revision.key,
      key: args.runKey,
      jobKey: request.jobKey ?? "",
      cacheStatus: "live",
      outdatedOnArrival: window.currentRevision !== request.revisionNumber,
      model: args.model,
      promptVersion: args.promptVersion,
      schemaVersion: args.schemaVersion,
      providerLabel: "live",
      costUsd: null,
      inputTokens: null,
      outputTokens: null,
      latencyMs: null,
      gaps: [],
      issues: [],
      noObservationReason: null,
      createdAt: new Date(now).toISOString(),
      publishedAt: now,
      state: "running",
    });
  },
});

export const addObservations = mutation({
  args: { secret: v.string(), runId: v.id("runs"), observations: v.array(scoutObservation) },
  handler: async (ctx, args) => {
    await requireWorker(args.secret);
    const run = await ctx.db.get(args.runId);
    if (!run) return 0;
    const existing = await ctx.db.query("observations").withIndex("by_run", (q) => q.eq("runId", run._id)).collect();
    const seen = new Set(existing.map((item) => item.key));
    let added = 0;
    for (const observation of args.observations) {
      if (seen.has(observation.key)) continue;
      seen.add(observation.key);
      await ctx.db.insert("observations", {
        ...observation,
        runId: run._id,
        windowId: run.windowId,
        submissionId: run.submissionId,
        revisionNumber: run.revisionNumber,
      });
      added += 1;
    }
    return added;
  },
});

export const closeRun = mutation({
  args: {
    secret: v.string(),
    requestId: v.id("analysisRequests"),
    runId: v.id("runs"),
    state: v.union(v.literal("succeeded"), v.literal("partial"), v.literal("cancelled"), v.literal("failed")),
    note: v.string(),
    narrative: v.optional(v.string()),
    trackedMs: v.optional(v.number()),
    jobKey: v.string(),
  },
  handler: async (ctx, args) => {
    await requireWorker(args.secret);
    const request = await ctx.db.get(args.requestId);
    if (!request) return false;
    const now = Date.now();
    await ctx.db.patch(args.runId, {
      state: args.state === "failed" ? "partial" : args.state,
      coverageNote: args.note,
      narrative: args.narrative,
      ...(args.trackedMs !== undefined ? { trackedMs: args.trackedMs } : {}),
    });
    const finished = args.state === "succeeded";
    await ctx.db.patch(request._id, {
      status: finished ? "succeeded" : "failed",
      stage: args.state,
      runId: args.runId,
      jobKey: args.jobKey,
      leaseUntil: undefined,
      errorCode: finished ? undefined : args.state,
      errorMessage: finished ? undefined : args.note,
      retryable: !finished,
      updatedAt: now,
    });
    return true;
  },
});

export const addCorrection = mutation({
  args: {
    secret: v.string(),
    requestId: v.id("analysisRequests"),
    frameId: v.string(),
    tMs: v.number(),
    reason: v.string(),
    boxes: v.array(v.object({ trackId: v.optional(v.number()), box, confidence: v.number() })),
  },
  handler: async (ctx, args) => {
    await requireWorker(args.secret);
    const request = await ctx.db.get(args.requestId);
    if (!request) return false;
    const window = await ctx.db.get(request.windowId);
    if (!window) return false;
    if (!window.frames.some((frame) => frame.frameId === args.frameId)) {
      await ctx.db.patch(window._id, { frames: [...window.frames, { frameId: args.frameId, tMs: args.tMs }] });
    }
    await ctx.db.insert("correctionRequests", {
      submissionId: window.submissionId,
      windowId: window._id,
      revisionNumber: request.revisionNumber,
      tMs: args.tMs,
      frameId: args.frameId,
      reason: args.reason,
      boxes: args.boxes,
      createdAt: Date.now(),
    });
    return true;
  },
});

const OPEN = new Set(["queued", "running"]);

export const profileInput = mutation({
  args: { secret: v.string(), requestId: v.id("analysisRequests") },
  handler: async (ctx, args) => {
    await requireWorker(args.secret);
    const request = await ctx.db.get(args.requestId);
    if (!request) return { ready: false as const };
    const submission = await ctx.db.get(request.submissionId);
    if (!submission) return { ready: false as const };
    const player = await ctx.db.get(submission.playerId);
    const windows = (
      await ctx.db
        .query("windows")
        .withIndex("by_submission", (q) => q.eq("submissionId", submission._id))
        .collect()
    )
      .filter((window) => (window.kind ?? "window") === "scout")
      .sort((a, b) => a.order - b.order);
    if (!windows.length) return { ready: false as const };
    for (const window of windows) {
      const latest = await ctx.db
        .query("analysisRequests")
        .withIndex("by_window", (q) => q.eq("windowId", window._id))
        .order("desc")
        .first();
      if (!latest || OPEN.has(latest.status)) return { ready: false as const };
    }
    const runs = await ctx.db
      .query("runs")
      .withIndex("by_submission", (q) => q.eq("submissionId", submission._id))
      .collect();
    const current = currentRuns(
      windows.map((window) => ({ id: window._id, currentRevision: window.currentRevision })),
      runs.map((run) => ({
        id: run._id,
        windowId: run.windowId,
        revisionNumber: run.revisionNumber,
        outdatedOnArrival: run.outdatedOnArrival,
        publishedAt: run.publishedAt,
      })),
    );
    const observations = await ctx.db
      .query("observations")
      .withIndex("by_submission", (q) => q.eq("submissionId", submission._id))
      .collect();
    const decisions = await ctx.db
      .query("decisions")
      .withIndex("by_submission", (q) => q.eq("submissionId", submission._id))
      .order("desc")
      .collect();
    const latestDecision = new Map<string, string>();
    for (const decision of decisions) {
      if (!latestDecision.has(decision.observationId)) latestDecision.set(decision.observationId, decision.action);
    }
    const runById = new Map(runs.map((run) => [run._id as string, run]));
    const clips = windows.map((window) => {
      const runId = current.get(window._id);
      const run = runId ? runById.get(runId) : undefined;
      const events = observations
        .filter((item) => item.windowId === window._id && runId !== undefined && item.runId === runId && latestDecision.get(item._id) !== "reject")
        .map((item) => ({
          id: item._id,
          action: item.action ?? "",
          outcome: item.outcomeDetail ?? item.outcome,
          text: item.visibleAction,
          startMs: item.startMs,
          held: item.attributionHold,
        }));
      return { order: window.order, trackedMs: run?.trackedMs ?? 0, events };
    });
    return {
      ready: true as const,
      playerName: player?.displayName ?? "",
      clips,
    };
  },
});

const profileAbility = v.object({
  overall: v.number(),
  dimensions: v.array(
    v.object({
      name: v.union(v.literal("ball_security"), v.literal("passing"), v.literal("carrying"), v.literal("involvement")),
      score: v.number(),
      reason: v.string(),
      eventIds: v.array(v.string()),
    }),
  ),
});

export const publishProfile = mutation({
  args: {
    secret: v.string(),
    requestId: v.id("analysisRequests"),
    key: v.string(),
    eventIds: v.array(v.string()),
    summary: v.string(),
    qualities: v.array(v.object({ text: v.string(), eventIds: v.array(v.string()) })),
    gaps: v.array(v.string()),
    ability: v.optional(profileAbility),
    model: v.string(),
    promptVersion: v.string(),
    costUsd: v.union(v.number(), v.null()),
    inputTokens: v.union(v.number(), v.null()),
    outputTokens: v.union(v.number(), v.null()),
    cacheStatus: v.string(),
  },
  handler: async (ctx, args) => {
    await requireWorker(args.secret);
    const request = await ctx.db.get(args.requestId);
    if (!request) return null;
    const existing = await ctx.db
      .query("profiles")
      .withIndex("by_submission_key", (q) => q.eq("submissionId", request.submissionId).eq("key", args.key))
      .unique();
    if (existing) return existing._id;
    const { secret: _secret, requestId: _requestId, ...profile } = args;
    return await ctx.db.insert("profiles", {
      ...profile,
      submissionId: request.submissionId,
      createdAt: Date.now(),
    });
  },
});

