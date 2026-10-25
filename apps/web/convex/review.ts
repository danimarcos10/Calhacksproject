import { ConvexError, v } from "convex/values";
import { mutation, query } from "./_generated/server";
import type { MutationCtx, QueryCtx } from "./_generated/server";
import type { Doc, Id } from "./_generated/dataModel";
import { cleanReviewer, openSubmission, sha256Hex } from "./lib/access";
import { currentRuns, decisionBlocked, momentStatus, silentRelabels, type DecisionAction } from "./lib/status";
import { evidenceConfidence } from "./lib/confidence";
import { buildScoutBrief } from "./lib/scoutBrief";
import { buildSummary } from "./lib/summary";
import { anchor } from "./schema";

// Coach-facing functions. Every call carries the submission key and its review
// code; the code is checked against a stored SHA-256 hash.

const access = { key: v.string(), code: v.string() };

async function windowsOf(ctx: QueryCtx, submissionId: Id<"submissions">) {
  return await ctx.db
    .query("windows")
    .withIndex("by_submission", (q) => q.eq("submissionId", submissionId))
    .collect();
}

async function revisionOf(ctx: QueryCtx, windowId: Id<"windows">, number: number) {
  if (number < 1) return null;
  return await ctx.db
    .query("revisions")
    .withIndex("by_window", (q) => q.eq("windowId", windowId).eq("number", number))
    .unique();
}

function prepEffort(window: Doc<"windows">, revisions: Doc<"revisions">[], current: Doc<"revisions"> | null) {
  const anchors = current?.anchors ?? [];
  return {
    manualBoxes: anchors.filter((a) => a.state === "located" && a.source !== "estimated" && a.method !== "confirmed_estimate").length,
    confirmedEstimates: anchors.filter((a) => a.method === "confirmed_estimate").length,
    estimatedBoxes: anchors.filter((a) => a.state === "located" && a.source === "estimated").length,
    notVisibleMarks: anchors.filter((a) => a.state === "not_visible").length,
    uncertainMarks: anchors.filter((a) => a.state === "uncertain").length,
    framesSampled: window.frames.length,
    saves: revisions.length,
    corrections: revisions.filter((r) => r.origin === "correction").length,
    importedFromM0: revisions.some((r) => r.origin === "imported"),
    proposalsOffered: revisions.reduce((sum, r) => sum + (r.proposed?.offered ?? 0), 0),
    proposalsKept: revisions.reduce((sum, r) => sum + (r.proposed?.kept ?? 0), 0),
  };
}

const LIVE_STATUS = new Set(["suggestion", "accepted", "held"]);

function profileAbility(ability: Doc<"profiles">["ability"], blocked: boolean, confidenceScore: number) {
  if (!ability || ability.dimensions.length < 2) {
    return { state: "withheld" as const, reason: "Not enough cited actions to estimate ability." };
  }
  if (blocked) return { state: "withheld" as const, reason: "A cited moment was rejected or is out of date." };
  if (confidenceScore < 40) {
    return { state: "withheld" as const, reason: "Evidence confidence is below 40, so this estimate stays hidden." };
  }
  return { state: "shown" as const, overall: ability.overall, dimensions: ability.dimensions };
}

function presentProfile(
  stored: Doc<"profiles"> | null,
  moments: { id: string; status: string }[],
  confidenceScore: number,
) {
  if (!stored) return null;
  const byId = new Map(moments.map((moment) => [moment.id, moment.status]));
  const live = (ids: string[]) => ids.every((id) => LIVE_STATUS.has(byId.get(id) ?? ""));
  const qualities = stored.qualities.filter((quality) => quality.eventIds.length > 0 && live(quality.eventIds));
  const cited = stored.ability?.dimensions.flatMap((dimension) => dimension.eventIds) ?? [];
  const blocked = cited.some((id) => {
    const status = byId.get(id);
    return status === undefined || status === "rejected" || status === "stale";
  });
  const ability = profileAbility(stored.ability, blocked, confidenceScore);
  return {
    summary: stored.summary,
    qualities,
    gaps: stored.gaps,
    ability,
    model: stored.model,
    cacheStatus: stored.cacheStatus,
    costUsd: stored.costUsd,
  };
}

async function loadReview(ctx: QueryCtx, submission: Doc<"submissions">) {
  const player = await ctx.db.get(submission.playerId);
  const windows = (await windowsOf(ctx, submission._id)).sort((a, b) => a.order - b.order);
  const runs = await ctx.db
    .query("runs")
    .withIndex("by_submission", (q) => q.eq("submissionId", submission._id))
    .collect();
  const current = currentRuns(
    windows.map((w) => ({ id: w._id, currentRevision: w.currentRevision })),
    runs.map((r) => ({ id: r._id, windowId: r.windowId, revisionNumber: r.revisionNumber, outdatedOnArrival: r.outdatedOnArrival, publishedAt: r.publishedAt })),
  );
  const currentRunIds = new Set(current.values());
  const observations = await ctx.db
    .query("observations")
    .withIndex("by_submission", (q) => q.eq("submissionId", submission._id))
    .collect();
  const decisions = await ctx.db
    .query("decisions")
    .withIndex("by_submission", (q) => q.eq("submissionId", submission._id))
    .order("asc")
    .collect();
  const history = new Map<string, Doc<"decisions">[]>();
  for (const decision of decisions) {
    history.set(decision.observationId, [...(history.get(decision.observationId) ?? []), decision]);
  }
  const windowById = new Map(windows.map((w) => [w._id as string, w]));
  const runById = new Map(runs.map((r) => [r._id as string, r]));

  const moments = observations
    .map((obs) => {
      const window = windowById.get(obs.windowId);
      const trail = history.get(obs._id) ?? [];
      const latest = trail[trail.length - 1];
      const status = momentStatus(currentRunIds.has(obs.runId), obs.attributionHold, latest?.action as DecisionAction | undefined);
      return {
        id: obs._id,
        key: obs.key,
        runId: obs.runId,
        runKey: runById.get(obs.runId)?.key ?? "",
        windowId: obs.windowId,
        windowOrder: window?.order ?? 0,
        videoKey: window?.videoKey ?? "",
        revisionNumber: obs.revisionNumber,
        category: obs.category,
        startMs: obs.startMs,
        endMs: obs.endMs,
        seekMs: obs.seekMs,
        frameIds: obs.frameIds,
        visibleAction: obs.visibleAction,
        outcome: obs.outcome,
        action: obs.action ?? null,
        outcomeDetail: obs.outcomeDetail ?? null,
        evidenceStatus: obs.evidenceStatus,
        identityStatus: obs.identityStatus,
        limitations: obs.limitations,
        holdReason: obs.holdReason,
        status,
        decision: latest ? { action: latest.action, reason: latest.reason ?? null, reviewer: latest.reviewer, at: latest.createdAt } : null,
        history: trail.map((d) => ({ action: d.action, reason: d.reason ?? null, reviewer: d.reviewer, at: d.createdAt })),
      };
    })
    .sort((a, b) => a.windowOrder - b.windowOrder || a.startMs - b.startMs);

  const windowViews = [];
  for (const window of windows) {
    const revisions = await ctx.db
      .query("revisions")
      .withIndex("by_window", (q) => q.eq("windowId", window._id))
      .collect();
    const revision = revisions.find((r) => r.number === window.currentRevision) ?? null;
    const requests = await ctx.db
      .query("analysisRequests")
      .withIndex("by_window", (q) => q.eq("windowId", window._id))
      .order("desc")
      .take(5);
    const runId = current.get(window._id) ?? null;
    const run = runId ? runById.get(runId) : undefined;
    windowViews.push({
      id: window._id,
      order: window.order,
      videoKey: window.videoKey,
      manifestKey: window.manifestKey,
      videoDurationMs: window.videoDurationMs,
      startMs: window.startMs,
      endMs: window.endMs,
      frames: window.frames,
      kind: window.kind ?? "window",
      link: window.link,
      currentRevision: window.currentRevision,
      revision: revision
        ? {
            number: revision.number,
            key: revision.key,
            anchors: revision.anchors,
            jerseyNote: revision.jerseyNote,
            teamColorNote: revision.teamColorNote,
            note: revision.note,
            origin: revision.origin,
            savedBy: revision.savedBy,
            createdAt: revision.createdAt,
          }
        : null,
      requests: requests.map((r) => ({
        id: r._id,
        status: r.status,
        stage: r.stage ?? null,
        attempt: r.attempt,
        revisionNumber: r.revisionNumber,
        errorCode: r.errorCode ?? null,
        errorMessage: r.errorMessage ?? null,
        retryable: r.retryable ?? null,
        progress: r.progress ?? null,
        cancelRequested: r.cancelRequested ?? false,
        requestedBy: r.requestedBy,
        createdAt: r.createdAt,
        updatedAt: r.updatedAt,
      })),
      currentRunId: runId,
      gaps: run?.gaps ?? [],
      noObservationReason: run?.noObservationReason ?? null,
      spend: window.spend ?? null,
      prep: prepEffort(window, revisions, revision),
    });
  }

  const note = await ctx.db
    .query("notes")
    .withIndex("by_submission", (q) => q.eq("submissionId", submission._id))
    .order("desc")
    .first();
  const footage = await ctx.db
    .query("footageRequests")
    .withIndex("by_submission", (q) => q.eq("submissionId", submission._id))
    .order("desc")
    .first();

  const summary = buildSummary(
    moments.map((m) => ({
      id: m.id,
      category: m.category,
      videoKey: m.videoKey,
      windowOrder: m.windowOrder,
      startMs: m.startMs,
      endMs: m.endMs,
      seekMs: m.seekMs,
      visibleAction: m.visibleAction,
      outcome: m.outcome,
      status: m.status,
    })),
    windowViews.map((w) => ({
      order: w.order,
      startMs: w.startMs,
      endMs: w.endMs,
      videoKey: w.videoKey,
      prepared: w.currentRevision > 0,
      analysed: w.currentRunId !== null,
      gaps: w.gaps,
      noObservationReason: w.noObservationReason,
    })),
  );

  const corrections = [];
  for (const window of windows) {
    const rows = await ctx.db
      .query("correctionRequests")
      .withIndex("by_window", (q) => q.eq("windowId", window._id))
      .order("desc")
      .take(3);
    for (const row of rows) {
      if (row.revisionNumber !== window.currentRevision) continue;
      corrections.push({
        id: row._id,
        windowId: row.windowId,
        tMs: row.tMs,
        frameId: row.frameId,
        reason: row.reason,
        boxes: row.boxes,
      });
    }
  }
  const confidence = evidenceConfidence(
    windows.map((window) => {
      const runId = current.get(window._id);
      const run = runId ? runById.get(runId) : undefined;
      return { order: window.order, trackedMs: run?.trackedMs ?? 0 };
    }),
    moments.map((moment) => ({
      windowOrder: moment.windowOrder,
      status: moment.status,
      outcome: moment.outcomeDetail ?? moment.outcome,
      attributionHold: moment.status === "held",
    })),
  );
  const storedProfile = await ctx.db
    .query("profiles")
    .withIndex("by_submission", (q) => q.eq("submissionId", submission._id))
    .order("desc")
    .first();

  const brief = buildScoutBrief(
    moments
      .filter((moment) => moment.action && (moment.status === "suggestion" || moment.status === "accepted" || moment.status === "held"))
      .map((moment) => ({
        id: moment.id,
        action: moment.action ?? "",
        outcome: moment.outcomeDetail ?? moment.outcome,
        startMs: moment.startMs,
        visibleAction: moment.visibleAction,
      })),
  );

  return {
    submission: {
      key: submission.key,
      title: submission.title,
      rightsNote: submission.rightsNote,
      player: player?.displayName ?? "Unnamed player",
    },
    windows: windowViews,
    moments,
    runs: runs
      .sort((a, b) => b.publishedAt - a.publishedAt)
      .map((r) => ({
        id: r._id,
        key: r.key,
        windowOrder: windowById.get(r.windowId)?.order ?? 0,
        revisionNumber: r.revisionNumber,
        current: currentRunIds.has(r._id),
        outdatedOnArrival: r.outdatedOnArrival,
        cacheStatus: r.cacheStatus,
        model: r.model,
        providerLabel: r.providerLabel,
        state: r.state ?? "succeeded",
        coverageNote: r.coverageNote ?? null,
        narrative: r.narrative ?? null,
        trackedMs: r.trackedMs ?? null,
        costUsd: r.costUsd,
        inputTokens: r.inputTokens,
        outputTokens: r.outputTokens,
        latencyMs: r.latencyMs,
        observationCount: observations.filter((o) => o.runId === r._id).length,
        publishedAt: r.publishedAt,
      })),
    brief,
    confidence,
    profile: presentProfile(storedProfile, moments, confidence.score),
    corrections,
    note: note ? { body: note.body, reviewer: note.reviewer, at: note.createdAt } : null,
    footageRequest: footage ? { body: footage.body, reviewer: footage.reviewer, at: footage.createdAt } : null,
    summary,
  };
}

export const get = query({
  args: access,
  handler: async (ctx, { key, code }) => loadReview(ctx, await openSubmission(ctx, key, code)),
});

export const inbox = query({
  args: { entries: v.array(v.object(access)) },
  handler: async (ctx, { entries }) => {
    const rows = [];
    for (const entry of entries.slice(0, 20)) {
      try {
        const submission = await openSubmission(ctx, entry.key, entry.code);
        const review = await loadReview(ctx, submission);
        rows.push({
          key: submission.key,
          ok: true as const,
          title: review.submission.title,
          player: review.submission.player,
          windows: review.windows.length,
          accepted: review.moments.filter((m) => m.status === "accepted").length,
          pending: review.summary.pending.length,
          queued: review.windows.filter((w) => w.requests[0]?.status === "queued" || w.requests[0]?.status === "running").length,
        });
      } catch {
        rows.push({ key: entry.key, ok: false as const });
      }
    }
    return rows;
  },
});

export const decide = mutation({
  args: {
    ...access,
    observationId: v.id("observations"),
    action: v.union(v.literal("accept"), v.literal("reject"), v.literal("reset")),
    reason: v.optional(v.string()),
    reviewer: v.string(),
  },
  handler: async (ctx, args) => {
    const submission = await openSubmission(ctx, args.key, args.code);
    const observation = await ctx.db.get(args.observationId);
    if (!observation || observation.submissionId !== submission._id) {
      throw new ConvexError({ code: "not_found", message: "That moment is not part of this submission." });
    }
    const windows = await windowsOf(ctx, submission._id);
    const runs = await ctx.db
      .query("runs")
      .withIndex("by_window", (q) => q.eq("windowId", observation.windowId))
      .collect();
    const current = currentRuns(
      windows.map((w) => ({ id: w._id, currentRevision: w.currentRevision })),
      runs.map((r) => ({ id: r._id, windowId: r.windowId, revisionNumber: r.revisionNumber, outdatedOnArrival: r.outdatedOnArrival, publishedAt: r.publishedAt })),
    );
    const latest = await ctx.db
      .query("decisions")
      .withIndex("by_observation", (q) => q.eq("observationId", observation._id))
      .order("desc")
      .first();
    const status = momentStatus(current.get(observation.windowId) === observation.runId, observation.attributionHold, latest?.action);
    const blocked = decisionBlocked(status, args.action);
    if (blocked) throw new ConvexError({ code: status === "stale" ? "stale_observation" : "identity_hold", message: blocked });
    const reason = args.reason?.trim().slice(0, 500);
    return await ctx.db.insert("decisions", {
      submissionId: submission._id,
      observationId: observation._id,
      runId: observation.runId,
      revisionNumber: observation.revisionNumber,
      action: args.action,
      reason: args.action === "reject" && reason ? reason : undefined,
      reviewer: cleanReviewer(args.reviewer),
      createdAt: Date.now(),
    });
  },
});

export const saveNote = mutation({
  args: { ...access, body: v.string(), reviewer: v.string() },
  handler: async (ctx, args) => {
    const submission = await openSubmission(ctx, args.key, args.code);
    return await ctx.db.insert("notes", {
      submissionId: submission._id,
      body: args.body.trim().slice(0, 4000),
      reviewer: cleanReviewer(args.reviewer),
      createdAt: Date.now(),
    });
  },
});

export const saveFootageRequest = mutation({
  args: { ...access, body: v.string(), reviewer: v.string() },
  handler: async (ctx, args) => {
    const submission = await openSubmission(ctx, args.key, args.code);
    return await ctx.db.insert("footageRequests", {
      submissionId: submission._id,
      body: args.body.trim().slice(0, 2000),
      reviewer: cleanReviewer(args.reviewer),
      createdAt: Date.now(),
    });
  },
});

export const saveRevision = mutation({
  args: {
    ...access,
    windowId: v.id("windows"),
    baseRevision: v.number(),
    anchors: v.array(anchor),
    jerseyNote: v.string(),
    teamColorNote: v.string(),
    note: v.string(),
    origin: v.union(v.literal("prepare"), v.literal("correction")),
    proposed: v.optional(v.object({ offered: v.number(), kept: v.number() })),
    reviewer: v.string(),
  },
  handler: async (ctx, args) => {
    const submission = await openSubmission(ctx, args.key, args.code);
    const window = await ctx.db.get(args.windowId);
    if (!window || window.submissionId !== submission._id) {
      throw new ConvexError({ code: "not_found", message: "That window is not part of this submission." });
    }
    if (args.baseRevision !== window.currentRevision) {
      throw new ConvexError({
        code: "revision_conflict",
        message: `Selection ${window.currentRevision} was saved after you started editing selection ${args.baseRevision}. Reload it before saving.`,
      });
    }
    const known = new Set(window.frames.map((f) => f.frameId));
    const seen = new Set<string>();
    for (const item of args.anchors) {
      if (!known.has(item.frameId)) throw new ConvexError({ code: "unknown_frame", message: `Frame ${item.frameId} is not in this window.` });
      if (seen.has(item.frameId)) throw new ConvexError({ code: "duplicate_anchor", message: `Frame ${item.frameId} has two marks.` });
      seen.add(item.frameId);
      if (item.state === "located" && !item.box) {
        throw new ConvexError({ code: "box_required", message: `Frame ${item.frameId} is marked located without a box.` });
      }
    }
    if (!args.anchors.some((a) => a.state === "located" && a.source !== "estimated")) {
      throw new ConvexError({ code: "anchor_required", message: "Draw the player's box on at least one frame yourself before saving." });
    }
    const previous = await revisionOf(ctx, window._id, window.currentRevision);
    const relabelled = silentRelabels(previous?.anchors ?? [], args.anchors);
    if (relabelled.length) {
      throw new ConvexError({
        code: "estimate_relabelled",
        message: `Estimated boxes on ${relabelled.join(", ")} would become manual without confirmation. Use Confirm on each one.`,
      });
    }
    const number = window.currentRevision + 1;
    const now = Date.now();
    const id = await ctx.db.insert("revisions", {
      windowId: window._id,
      submissionId: submission._id,
      number,
      key: "pending",
      anchors: args.anchors,
      jerseyNote: args.jerseyNote.trim(),
      teamColorNote: args.teamColorNote.trim(),
      note: args.note.trim(),
      origin: args.origin,
      savedBy: cleanReviewer(args.reviewer),
      proposed: args.proposed,
      createdAt: now,
    });
    await ctx.db.patch(id, { key: `rev_${(await sha256Hex(id)).slice(0, 16)}` });
    await ctx.db.patch(window._id, { currentRevision: number });
    const waiting = await ctx.db
      .query("analysisRequests")
      .withIndex("by_window", (q) => q.eq("windowId", window._id))
      .collect();
    for (const request of waiting) {
      if (request.status === "queued" && request.revisionNumber < number) {
        await ctx.db.patch(request._id, {
          status: "outdated",
          errorCode: "outdated_revision",
          errorMessage: "The player selection changed before this analysis started.",
          updatedAt: now,
        });
      }
    }
    return { number };
  },
});

export const cancelAnalysis = mutation({
  args: { ...access, windowId: v.id("windows") },
  handler: async (ctx, args) => {
    const submission = await openSubmission(ctx, args.key, args.code);
    const window = await ctx.db.get(args.windowId);
    if (!window || window.submissionId !== submission._id) {
      throw new ConvexError({ code: "not_found", message: "That window is not part of this submission." });
    }
    const running = await ctx.db
      .query("analysisRequests")
      .withIndex("by_window", (q) => q.eq("windowId", window._id))
      .order("desc")
      .take(5);
    const current = running.find((item) => item.status === "running" || item.status === "queued");
    if (!current) return false;
    await ctx.db.patch(current._id, { cancelRequested: true, updatedAt: Date.now() });
    return true;
  },
});

export const queueAnalysis = mutation({
  args: { ...access, windowId: v.id("windows"), reviewer: v.string() },
  handler: async (ctx, args) => {
    const submission = await openSubmission(ctx, args.key, args.code);
    const window = await ctx.db.get(args.windowId);
    if (!window || window.submissionId !== submission._id) {
      throw new ConvexError({ code: "not_found", message: "That window is not part of this submission." });
    }
    return await enqueue(ctx, window, cleanReviewer(args.reviewer));
  },
});

export const queueAll = mutation({
  args: { ...access, reviewer: v.string() },
  handler: async (ctx, args) => {
    const submission = await openSubmission(ctx, args.key, args.code);
    const windows = (await windowsOf(ctx, submission._id)).sort((a, b) => a.order - b.order);
    const results = [];
    for (const window of windows) {
      if (window.currentRevision < 1) continue;
      results.push({ order: window.order, ...(await enqueue(ctx, window, cleanReviewer(args.reviewer))) });
    }
    return results;
  },
});

async function enqueue(ctx: MutationCtx, window: Doc<"windows">, reviewer: string) {
  if (window.currentRevision < 1) {
    throw new ConvexError({ code: "not_prepared", message: "Mark the player on this window before analysing it." });
  }
  const requests = await ctx.db
    .query("analysisRequests")
    .withIndex("by_window", (q) => q.eq("windowId", window._id))
    .collect();
  const active = requests.find(
    (r) => r.revisionNumber === window.currentRevision && (r.status === "queued" || r.status === "running"),
  );
  if (active) return { status: "already_queued" as const, requestId: active._id };
  const done = requests.find((r) => r.revisionNumber === window.currentRevision && r.status === "succeeded");
  if (done) return { status: "already_analysed" as const, requestId: done._id };
  const revision = await revisionOf(ctx, window._id, window.currentRevision);
  if (!revision) throw new ConvexError({ code: "not_prepared", message: "The current player selection is missing." });
  const now = Date.now();
  const requestId = await ctx.db.insert("analysisRequests", {
    windowId: window._id,
    submissionId: window.submissionId,
    revisionId: revision._id,
    revisionNumber: revision.number,
    status: "queued",
    attempt: 0,
    requestedBy: reviewer,
    createdAt: now,
    updatedAt: now,
    ...(window.kind ? { kind: window.kind } : {}),
  });
  return { status: "queued" as const, requestId };
}
