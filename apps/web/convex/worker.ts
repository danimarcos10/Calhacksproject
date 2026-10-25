import { ConvexError, v } from "convex/values";
import { mutation } from "./_generated/server";
import type { Doc, Id } from "./_generated/dataModel";
import type { MutationCtx } from "./_generated/server";
import { requireWorker } from "./lib/access";
import { anchor, spend } from "./schema";

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
        window: { videoKey: window.videoKey, manifestKey: window.manifestKey },
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
  args: { secret: v.string(), requestId: v.id("analysisRequests"), stage: v.string(), jobKey: v.string() },
  handler: async (ctx, { secret, requestId, stage, jobKey }) => {
    await requireWorker(secret);
    const request = await ctx.db.get(requestId);
    if (!request || request.status !== "running") return false;
    const now = Date.now();
    await ctx.db.patch(requestId, { stage, jobKey, leaseUntil: now + LEASE_MS, updatedAt: now });
    return true;
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
