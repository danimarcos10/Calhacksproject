import { ConvexError } from "convex/values";
import type { QueryCtx } from "../_generated/server";
import type { Doc } from "../_generated/dataModel";

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function sameDigest(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function openSubmission(ctx: QueryCtx, key: string, code: string): Promise<Doc<"submissions">> {
  const submission = await ctx.db
    .query("submissions")
    .withIndex("by_key", (q) => q.eq("key", key))
    .unique();
  if (!submission || !sameDigest(await sha256Hex(code.trim()), submission.accessHash)) {
    throw new ConvexError({ code: "no_access", message: "This review link does not open a submission. Ask for a new link." });
  }
  return submission;
}

export async function requireWorker(secret: string): Promise<void> {
  const expected = process.env.WORKER_SECRET;
  if (!expected || !sameDigest(await sha256Hex(secret), await sha256Hex(expected))) {
    throw new ConvexError({ code: "worker_unauthorized", message: "Worker secret rejected." });
  }
}

export function cleanReviewer(name: string): string {
  const trimmed = name.trim().slice(0, 40);
  return trimmed || "Coach";
}
