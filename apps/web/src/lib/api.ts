import type { components } from "./api.generated";

export const API_ORIGIN = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";

type Schemas = components["schemas"];

export type Frame = Schemas["FrameOut"];
export type Manifest = Schemas["ManifestOut"];
export type Anchor = Schemas["AnchorIn"];
export type Revision = Schemas["RevisionOut"];
export type VideoDetail = Schemas["VideoOut"];
export type Observation = Schemas["ObservationOut"];
export type Analysis = Schemas["AnalysisOut"];
export type Job = Schemas["JobOut"];
export type ProviderStatus = Schemas["ProviderOut"];

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
  }
}

async function parse<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(body.user_message || "The request failed.");
  }
  return body as T;
}

export function uploadClip(file: File, rightsNote: string, onProgress: (fraction: number) => void) {
  return new Promise<VideoDetail>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_ORIGIN}/api/videos`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      const body = JSON.parse(xhr.responseText || "{}");
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as VideoDetail);
      else reject(new ApiError(body.user_message || "The upload failed."));
    };
    xhr.onerror = () => reject(new ApiError("The upload failed."));
    const data = new FormData();
    data.append("file", file);
    data.append("rights_note", rightsNote);
    xhr.send(data);
  });
}

export async function getVideo(id: string) {
  return parse<VideoDetail>(await fetch(`${API_ORIGIN}/api/videos/${id}`));
}

export async function sampleWindow(videoId: string, startMs: number, endMs: number) {
  return parse<Manifest>(
    await fetch(`${API_ORIGIN}/api/videos/${videoId}/samples`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_ms: startMs, end_ms: endMs }),
    }),
  );
}

export async function proposeLocations(videoId: string, body: { manifest_id: string; anchors: Anchor[] }) {
  return parse<{ anchors: Anchor[] }>(
    await fetch(`${API_ORIGIN}/api/videos/${videoId}/proposals`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function saveTarget(videoId: string, body: Schemas["TargetRequest"]) {
  return parse<Revision>(
    await fetch(`${API_ORIGIN}/api/videos/${videoId}/targets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function startAnalysis(videoId: string, manifestId: string, revisionId: string, idempotencyKey: string) {
  return parse<Job>(
    await fetch(`${API_ORIGIN}/api/analyses`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ video_id: videoId, manifest_id: manifestId, target_revision_id: revisionId }),
    }),
  );
}

export async function getJob(id: string) {
  return parse<Job>(await fetch(`${API_ORIGIN}/api/jobs/${id}`));
}

export async function peopleAt(videoId: string, tMs: number) {
  return parse<{ t_ms: number; people: { box: Anchor["box"]; confidence: number }[] }>(
    await fetch(`${API_ORIGIN}/api/videos/${videoId}/people?t=${tMs}`),
  );
}

export type ClipStats = {
  tracked_s: number;
  receives: number;
  passes_completed: number;
  passes_attempted: number;
  carries: number;
  losses: number;
  reviewed: boolean;
  clips: number;
  confidence: number;
};

export type League = "mls_next" | "ecnl" | "ecnl_rl" | "npl" | "usys" | "high_school" | "club";

export type Program = {
  school: string;
  short_name: string;
  city: string;
  state: string;
  conference: string;
  division: "d1" | "d2";
  fit: "fit" | "possible" | "reach";
  fit_reason: string;
};

export type ReachStep = {
  title: string;
  detail: string;
  cost: "free" | "low cost";
};

export type ReachPlan = {
  school: string;
  division: "d1" | "d2";
  conference: string;
  reason: string;
  read: string;
  steps: ReachStep[];
  source: "claude" | "standard";
};

export type ProgramList = {
  programs: Program[];
  divisions: ("d1" | "d2")[];
  rule: string;
  note: string;
  run_ids: string[];
  actors: string[];
  cache_status: "live" | "cached";
  retrieved_at: string;
  message: string | null;
};

export type CoachCard = {
  school: string;
  division: "d1" | "d2";
  conference: string;
  coach_name: string | null;
  title: string | null;
  email: string | null;
  phone: string | null;
  url: string | null;
  subject: string;
  draft: string;
};

export type CoachResult = {
  result_id: string;
  review_id: string;
  player_email: string;
  cards: CoachCard[];
  summary: string;
  stats_table: string;
  rule: string;
  run_ids: string[];
  actors: string[];
  cache_status: "live" | "cached";
  retrieved_at: string;
  message: string | null;
};

export async function listPrograms(reviewId: string, body: { state: string; league: League }) {
  return parse<ProgramList>(
    await fetch(`${API_ORIGIN}/api/reviews/${reviewId}/programs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(180000),
    }),
  );
}

export async function findCoaches(
  reviewId: string,
  body: {
    player_name: string;
    player_email: string;
    position: string;
    grad_year: number;
    state: string;
    league: League;
    clip_url: string;
    schools: string[];
    stats: ClipStats;
    profile?: string;
  },
) {
  return parse<CoachResult>(
    await fetch(`${API_ORIGIN}/api/reviews/${reviewId}/opportunities`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(180000),
    }),
  );
}

export async function getReachPlan(
  reviewId: string,
  body: {
    position: string;
    grad_year: number;
    state: string;
    league: League;
    school: string;
    stats: ClipStats;
    profile?: string;
  },
) {
  return parse<ReachPlan>(
    await fetch(`${API_ORIGIN}/api/reviews/${reviewId}/reach-plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(60000),
    }),
  );
}

export async function sendOutreach(
  reviewId: string,
  body: { result_id: string; email: string; subject: string; body: string; reply_to: string },
) {
  return parse<{ sent_to: string; test_mode: boolean; message: string }>(
    await fetch(`${API_ORIGIN}/api/reviews/${reviewId}/outreach`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30000),
    }),
  );
}

export async function startScoutBatch(body: {
  player_name: string;
  clips: { video_id: string; t_ms: number; box: NonNullable<Anchor["box"]>; marks?: { t_ms: number; box: NonNullable<Anchor["box"]> }[] }[];
}) {
  return parse<{ key: string; code: string; window_id: string; window_ids: string[] }>(
    await fetch(`${API_ORIGIN}/api/scout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function stickPlayer(videoId: string, body: { t_ms: number; box: NonNullable<Anchor["box"]> }) {
  return parse<{ frames: { t: number; box: NonNullable<Anchor["box"]> }[]; message: string }>(
    await fetch(`${API_ORIGIN}/api/videos/${videoId}/stick`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(60000),
    }),
  );
}

export async function findPlayer(videoId: string, description: string) {
  return parse<{ found: boolean; t_ms: number; track_id: number | null; box: NonNullable<Anchor["box"]> | null; message: string }>(
    await fetch(`${API_ORIGIN}/api/videos/${videoId}/find-player`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description }),
      signal: AbortSignal.timeout(60000),
    }),
  );
}

export async function startScout(videoId: string, body: { t_ms: number; box: NonNullable<Anchor["box"]>; player_name: string }) {
  return parse<{ key: string; code: string; window_id: string }>(
    await fetch(`${API_ORIGIN}/api/videos/${videoId}/scout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function getReady() {
  const response = await fetch(`${API_ORIGIN}/readyz`);
  return (await response.json()) as Schemas["ReadyOut"];
}

export function formatMs(ms: number) {
  const total = Math.max(0, ms) / 1000;
  const minutes = Math.floor(total / 60);
  const seconds = total - minutes * 60;
  return `${minutes}:${seconds.toFixed(3).padStart(6, "0")}`;
}
