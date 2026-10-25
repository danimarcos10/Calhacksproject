import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
  id TEXT PRIMARY KEY,
  sha256 TEXT NOT NULL,
  original_path TEXT NOT NULL,
  playback_path TEXT NOT NULL,
  duration_ms INTEGER NOT NULL,
  timeline_ms INTEGER NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  rotation INTEGER NOT NULL,
  codec TEXT NOT NULL,
  frame_rate TEXT,
  first_pts REAL NOT NULL,
  metadata_json TEXT NOT NULL,
  rights_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS manifests (
  id TEXT PRIMARY KEY,
  video_id TEXT NOT NULL,
  start_ms INTEGER NOT NULL,
  end_ms INTEGER NOT NULL,
  sampler_version TEXT NOT NULL,
  frames_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS target_revisions (
  id TEXT PRIMARY KEY,
  video_id TEXT NOT NULL,
  manifest_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  anchors_json TEXT NOT NULL,
  jersey_note TEXT NOT NULL,
  team_color_note TEXT NOT NULL,
  identity_uncertain INTEGER NOT NULL,
  role TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE(video_id, revision)
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  video_id TEXT NOT NULL,
  manifest_id TEXT NOT NULL,
  target_revision_id TEXT NOT NULL,
  status TEXT NOT NULL,
  stage TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  error_message TEXT,
  error_retryable INTEGER,
  result_run_id TEXT,
  idempotency_key TEXT,
  fingerprint TEXT NOT NULL,
  cache_status TEXT NOT NULL,
  stage_log_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_idem ON jobs(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS analysis_runs (
  id TEXT PRIMARY KEY,
  video_id TEXT NOT NULL,
  manifest_id TEXT NOT NULL,
  target_revision_id TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  model_requested TEXT NOT NULL,
  model_returned TEXT,
  prompt_version TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  sampler_version TEXT NOT NULL,
  status TEXT NOT NULL,
  provider_label TEXT NOT NULL,
  usage_json TEXT,
  cost_usd REAL,
  latency_ms INTEGER,
  stop_reason TEXT,
  request_id TEXT,
  gaps_json TEXT,
  issues_json TEXT,
  resample_json TEXT,
  no_observation_reason TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  category TEXT NOT NULL,
  start_ms INTEGER NOT NULL,
  end_ms INTEGER NOT NULL,
  frame_ids_json TEXT NOT NULL,
  visible_action TEXT NOT NULL,
  outcome TEXT NOT NULL,
  evidence_status TEXT NOT NULL,
  identity_status TEXT NOT NULL,
  limitations_json TEXT NOT NULL,
  review_status TEXT NOT NULL,
  attribution_hold INTEGER NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attached_manifests (
  manifest_id TEXT PRIMARY KEY,
  submission_key TEXT NOT NULL,
  attached_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS budget_entries (
  id TEXT PRIMARY KEY,
  reservation_id TEXT NOT NULL,
  job_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  amount_usd REAL NOT NULL,
  input_tokens INTEGER,
  output_tokens INTEGER,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_attempts (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  batch_key TEXT NOT NULL,
  state TEXT NOT NULL,
  reservation_id TEXT,
  fingerprint TEXT NOT NULL,
  response_json TEXT,
  tries INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(job_id, batch_key)
);
CREATE TABLE IF NOT EXISTS scout_cache (
  fingerprint TEXT PRIMARY KEY,
  response_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS opportunity_cache (
  fingerprint TEXT PRIMARY KEY,
  response_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outreach_sends (
  id TEXT PRIMARY KEY,
  review_id TEXT NOT NULL,
  result_id TEXT NOT NULL,
  coach_email TEXT NOT NULL,
  delivered_to TEXT NOT NULL,
  subject TEXT NOT NULL,
  test_mode INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(review_id, coach_email)
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.executescript(SCHEMA)
            self._ensure_column("target_revisions", "note", "note TEXT NOT NULL DEFAULT ''")
            self._ensure_column("observations", "detail_json", "detail_json TEXT NOT NULL DEFAULT '{}'")

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        if column not in {row[1] for row in rows}:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self._conn.execute(sql, params).fetchall()]

    def query_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def mark_interrupted(self) -> None:
        now = utcnow()
        self.execute(
            """
            UPDATE jobs
            SET status='interrupted', stage='interrupted', error_code='interrupted',
                error_message=?, error_retryable=1, finished_at=?
            WHERE status='running'
            """,
            (
                "Analysis stopped because the server restarted. The upload and target are still here; retry the analysis.",
                now,
            ),
        )
        # A call that left the machine may already have been billed. Never resend it.
        self.execute(
            "UPDATE model_attempts SET state='unknown', updated_at=? WHERE state='sent'",
            (now,),
        )

    def insert_video(self, row: dict[str, Any]) -> None:
        self.execute(
            """
            INSERT INTO videos (
              id, sha256, original_path, playback_path, duration_ms, timeline_ms,
              width, height, rotation, codec, frame_rate, first_pts, metadata_json,
              rights_note, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["id"],
                row["sha256"],
                row["original_path"],
                row["playback_path"],
                row["duration_ms"],
                row["timeline_ms"],
                row["width"],
                row["height"],
                row["rotation"],
                row["codec"],
                row["frame_rate"],
                row["first_pts"],
                json.dumps(row["metadata"]),
                row["rights_note"],
                row["created_at"],
            ),
        )

    def get_video(self, video_id: str) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM videos WHERE id=?", (video_id,))

    def insert_manifest(self, row: dict[str, Any]) -> None:
        self.execute(
            """
            INSERT INTO manifests (id, video_id, start_ms, end_ms, sampler_version, frames_json, created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                row["id"],
                row["video_id"],
                row["start_ms"],
                row["end_ms"],
                row["sampler_version"],
                json.dumps(row["frames"]),
                row["created_at"],
            ),
        )

    def get_manifest(self, manifest_id: str) -> dict[str, Any] | None:
        row = self.query_one("SELECT * FROM manifests WHERE id=?", (manifest_id,))
        if row:
            row["frames"] = json.loads(row["frames_json"])
        return row

    def manifests_for_video(self, video_id: str) -> list[dict[str, Any]]:
        rows = self.query(
            "SELECT * FROM manifests WHERE video_id=? ORDER BY created_at",
            (video_id,),
        )
        for row in rows:
            row["frames"] = json.loads(row["frames_json"])
        return rows

    def insert_revision(self, row: dict[str, Any]) -> None:
        self.execute(
            """
            INSERT INTO target_revisions (
              id, video_id, manifest_id, revision, anchors_json, jersey_note,
              team_color_note, identity_uncertain, role, note, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["id"],
                row["video_id"],
                row["manifest_id"],
                row["revision"],
                json.dumps(row["anchors"]),
                row["jersey_note"],
                row["team_color_note"],
                1 if row["identity_uncertain"] else 0,
                row["role"],
                row.get("note") or "",
                row["created_at"],
            ),
        )

    def get_revision(self, revision_id: str) -> dict[str, Any] | None:
        row = self.query_one("SELECT * FROM target_revisions WHERE id=?", (revision_id,))
        if row:
            row["anchors"] = json.loads(row["anchors_json"])
            row["identity_uncertain"] = bool(row["identity_uncertain"])
        return row

    def latest_revision(self, video_id: str) -> dict[str, Any] | None:
        row = self.query_one(
            "SELECT * FROM target_revisions WHERE video_id=? ORDER BY revision DESC LIMIT 1",
            (video_id,),
        )
        if row:
            row["anchors"] = json.loads(row["anchors_json"])
            row["identity_uncertain"] = bool(row["identity_uncertain"])
        return row

    def latest_revision_for_manifest(self, manifest_id: str) -> dict[str, Any] | None:
        row = self.query_one(
            "SELECT * FROM target_revisions WHERE manifest_id=? ORDER BY revision DESC LIMIT 1",
            (manifest_id,),
        )
        if row:
            row["anchors"] = json.loads(row["anchors_json"])
            row["identity_uncertain"] = bool(row["identity_uncertain"])
        return row

    def attach_manifest(self, manifest_id: str, submission_key: str) -> None:
        self.execute(
            "INSERT OR IGNORE INTO attached_manifests (manifest_id, submission_key, attached_at) VALUES (?,?,?)",
            (manifest_id, submission_key, utcnow()),
        )

    def attachment(self, manifest_id: str) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM attached_manifests WHERE manifest_id=?", (manifest_id,))

    def active_job_for_fingerprint(self, digest: str) -> dict[str, Any] | None:
        row = self.query_one(
            "SELECT id FROM jobs WHERE fingerprint=? AND status IN ('queued','running') ORDER BY created_at LIMIT 1",
            (digest,),
        )
        return self.get_job(row["id"]) if row else None

    def manifest_spend(self, manifest_id: str) -> dict[str, Any]:
        jobs = self.query(
            """
            SELECT j.id, j.status, j.cache_status, r.provider_label
            FROM jobs j LEFT JOIN analysis_runs r ON r.id = j.result_run_id
            WHERE j.manifest_id=?
            """,
            (manifest_id,),
        )
        reconciled = 0.0
        live_calls = 0
        synthetic_calls = 0
        unknown = 0
        failed = 0
        cached = 0
        for job in jobs:
            if job["status"] == "failed":
                failed += 1
            if job["cache_status"] == "cached":
                cached += 1
            for entry in self.query("SELECT kind, amount_usd, input_tokens FROM budget_entries WHERE job_id=?", (job["id"],)):
                if entry["kind"] == "reconcile":
                    if job["provider_label"] == "synthetic":
                        synthetic_calls += 1
                    else:
                        live_calls += 1
                        reconciled += float(entry["amount_usd"])
                elif entry["kind"] == "release" and entry["input_tokens"] is None:
                    unknown += 1
        return {
            "reconciled_usd": round(reconciled, 6),
            "live_calls": live_calls,
            "synthetic_calls": synthetic_calls,
            "unknown_usage_attempts": unknown,
            "failed_jobs": failed,
            "cached_reuses": cached,
        }

    def revisions_for_video(self, video_id: str) -> list[dict[str, Any]]:
        rows = self.query(
            "SELECT * FROM target_revisions WHERE video_id=? ORDER BY revision",
            (video_id,),
        )
        for row in rows:
            row["anchors"] = json.loads(row["anchors_json"])
            row["identity_uncertain"] = bool(row["identity_uncertain"])
        return rows

    def next_revision_number(self, video_id: str) -> int:
        row = self.query_one(
            "SELECT COALESCE(MAX(revision), 0) AS n FROM target_revisions WHERE video_id=?",
            (video_id,),
        )
        return int(row["n"]) + 1 if row else 1

    def insert_job(self, row: dict[str, Any]) -> None:
        self.execute(
            """
            INSERT INTO jobs (
              id, video_id, manifest_id, target_revision_id, status, stage, attempts,
              error_code, error_message, error_retryable, result_run_id, idempotency_key,
              fingerprint, cache_status, stage_log_json, created_at, started_at, finished_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["id"],
                row["video_id"],
                row["manifest_id"],
                row["target_revision_id"],
                row["status"],
                row["stage"],
                row.get("attempts", 0),
                row.get("error_code"),
                row.get("error_message"),
                row.get("error_retryable"),
                row.get("result_run_id"),
                row.get("idempotency_key"),
                row["fingerprint"],
                row["cache_status"],
                json.dumps(row["stage_log"]),
                row["created_at"],
                row.get("started_at"),
                row.get("finished_at"),
            ),
        )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if row:
            row["stage_log"] = json.loads(row["stage_log_json"])
            if row["error_retryable"] is not None:
                row["error_retryable"] = bool(row["error_retryable"])
        return row

    def job_by_idempotency(self, key: str) -> dict[str, Any] | None:
        row = self.query_one("SELECT id FROM jobs WHERE idempotency_key=?", (key,))
        return self.get_job(row["id"]) if row else None

    def claim_next_job(self) -> str | None:
        with self.transaction():
            row = self._conn.execute(
                "SELECT id FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            now = utcnow()
            current = self._conn.execute("SELECT stage_log_json FROM jobs WHERE id=?", (row["id"],)).fetchone()
            log = json.loads(current["stage_log_json"]) if current else []
            log.append({"stage": "validating_input", "at": now})
            self._conn.execute(
                """
                UPDATE jobs
                SET status='running', stage='validating_input', started_at=?,
                    stage_log_json=?
                WHERE id=? AND status='queued'
                """,
                (now, json.dumps(log), row["id"]),
            )
            return str(row["id"])

    def set_stage(self, job_id: str, stage: str) -> None:
        with self.transaction():
            row = self._conn.execute("SELECT stage_log_json FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return
            log = json.loads(row["stage_log_json"])
            log.append({"stage": stage, "at": utcnow()})
            self._conn.execute(
                "UPDATE jobs SET stage=?, stage_log_json=? WHERE id=?",
                (stage, json.dumps(log), job_id),
            )

    def set_attempts(self, job_id: str, attempts: int) -> None:
        self.execute("UPDATE jobs SET attempts=? WHERE id=?", (attempts, job_id))

    def finish_job(
        self,
        job_id: str,
        *,
        status: str,
        stage: str,
        result_run_id: str | None = None,
        cache_status: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        error_retryable: bool | None = None,
    ) -> None:
        with self.transaction():
            row = self._conn.execute("SELECT stage_log_json, cache_status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return
            log = json.loads(row["stage_log_json"])
            log.append({"stage": stage, "at": utcnow()})
            self._conn.execute(
                """
                UPDATE jobs
                SET status=?, stage=?, result_run_id=COALESCE(?, result_run_id),
                    cache_status=?, error_code=?, error_message=?, error_retryable=?,
                    stage_log_json=?, finished_at=?
                WHERE id=?
                """,
                (
                    status,
                    stage,
                    result_run_id,
                    cache_status or row["cache_status"],
                    error_code,
                    error_message,
                    None if error_retryable is None else int(error_retryable),
                    json.dumps(log),
                    utcnow(),
                    job_id,
                ),
            )

    def find_succeeded_run(self, fingerprint: str) -> dict[str, Any] | None:
        return self.query_one(
            "SELECT * FROM analysis_runs WHERE input_hash=? AND status='succeeded' ORDER BY created_at LIMIT 1",
            (fingerprint,),
        )

    def insert_run(self, row: dict[str, Any]) -> None:
        self.execute(
            """
            INSERT INTO analysis_runs (
              id, video_id, manifest_id, target_revision_id, input_hash, model_requested,
              model_returned, prompt_version, schema_version, sampler_version, status,
              provider_label, usage_json, cost_usd, latency_ms, stop_reason, request_id,
              gaps_json, issues_json, resample_json, no_observation_reason, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["id"],
                row["video_id"],
                row["manifest_id"],
                row["target_revision_id"],
                row["input_hash"],
                row["model_requested"],
                row.get("model_returned"),
                row["prompt_version"],
                row["schema_version"],
                row["sampler_version"],
                row["status"],
                row["provider_label"],
                json.dumps(row.get("usage") or {}),
                row.get("cost_usd"),
                row.get("latency_ms"),
                row.get("stop_reason"),
                row.get("request_id"),
                json.dumps(row.get("gaps") or []),
                json.dumps(row.get("issues") or []),
                json.dumps(row.get("resample")),
                row.get("no_observation_reason"),
                row["created_at"],
            ),
        )

    def insert_observation(self, row: dict[str, Any]) -> None:
        self.execute(
            """
            INSERT INTO observations (
              id, run_id, category, start_ms, end_ms, frame_ids_json, visible_action,
              outcome, evidence_status, identity_status, limitations_json, review_status,
              attribution_hold, detail_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["id"],
                row["run_id"],
                row["category"],
                row["start_ms"],
                row["end_ms"],
                json.dumps(row["frame_ids"]),
                row["visible_action"],
                row["outcome"],
                row["evidence_status"],
                row["identity_status"],
                json.dumps(row["limitations"]),
                row["review_status"],
                1 if row["attribution_hold"] else 0,
                json.dumps(
                    {
                        "seek_ms": row.get("seek_ms", row["start_ms"]),
                        "continuity_issues": row.get("continuity_issues") or [],
                        "hold_reason": row.get("hold_reason") or "",
                        "hold_frame_id": row.get("hold_frame_id"),
                    }
                ),
                row["created_at"],
            ),
        )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.query_one("SELECT * FROM analysis_runs WHERE id=?", (run_id,))
        if not row:
            return None
        row["usage"] = json.loads(row["usage_json"] or "{}")
        row["gaps"] = json.loads(row["gaps_json"] or "[]")
        row["issues"] = json.loads(row["issues_json"] or "[]")
        row["resample"] = json.loads(row["resample_json"] or "null")
        return row

    def observations_for_run(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.query("SELECT * FROM observations WHERE run_id=? ORDER BY start_ms", (run_id,))
        for row in rows:
            row["frame_ids"] = json.loads(row["frame_ids_json"])
            row["limitations"] = json.loads(row["limitations_json"])
            row["attribution_hold"] = bool(row["attribution_hold"])
            detail = json.loads(row.get("detail_json") or "{}")
            row["seek_ms"] = int(detail.get("seek_ms", row["start_ms"]))
            row["continuity_issues"] = detail.get("continuity_issues") or []
            row["hold_reason"] = detail.get("hold_reason") or ""
            row["hold_frame_id"] = detail.get("hold_frame_id")
        return rows

    def save_succeeded_analysis(self, run: dict[str, Any], observations: list[dict[str, Any]], job_id: str) -> None:
        with self.transaction():
            self.insert_run(run)
            for observation in observations:
                self.insert_observation(observation)
            row = self._conn.execute(
                "SELECT stage_log_json, cache_status FROM jobs WHERE id=?",
                (job_id,),
            ).fetchone()
            log = json.loads(row["stage_log_json"])
            now = utcnow()
            log.append({"stage": "succeeded", "at": now})
            self._conn.execute(
                """
                UPDATE jobs
                SET status='succeeded', stage='succeeded', result_run_id=?, cache_status=?,
                    stage_log_json=?, finished_at=?, error_code=NULL, error_message=NULL
                WHERE id=?
                """,
                (run["id"], row["cache_status"], json.dumps(log), now, job_id),
            )

    def count_observations(self, run_id: str) -> int:
        row = self.query_one("SELECT COUNT(*) AS n FROM observations WHERE run_id=?", (run_id,))
        return int(row["n"]) if row else 0

    def add_budget(
        self,
        *,
        reservation_id: str,
        job_id: str,
        kind: str,
        amount_usd: float,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        self.execute(
            """
            INSERT INTO budget_entries (
              id, reservation_id, job_id, kind, amount_usd, input_tokens, output_tokens, created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                new_id("bud"),
                reservation_id,
                job_id,
                kind,
                amount_usd,
                input_tokens,
                output_tokens,
                utcnow(),
            ),
        )

    def committed_usd(self) -> float:
        row = self.query_one(
            "SELECT COALESCE(SUM(amount_usd), 0) AS n FROM budget_entries WHERE kind='reconcile'"
        )
        return float(row["n"]) if row else 0.0

    def reserved_usd(self) -> float:
        row = self.query_one(
            """
            SELECT COALESCE(SUM(amount_usd), 0) AS n FROM budget_entries
            WHERE kind='reserve' AND reservation_id NOT IN (
              SELECT reservation_id FROM budget_entries WHERE kind IN ('reconcile', 'release')
            )
            """
        )
        return float(row["n"]) if row else 0.0

    def get_attempt(self, job_id: str, batch_key: str) -> dict[str, Any] | None:
        return self.query_one(
            "SELECT * FROM model_attempts WHERE job_id=? AND batch_key=?",
            (job_id, batch_key),
        )

    def upsert_attempt(self, **fields: Any) -> None:
        current = self.get_attempt(fields["job_id"], fields["batch_key"])
        now = utcnow()
        if current is None:
            self.execute(
                """
                INSERT INTO model_attempts (
                  id, job_id, batch_key, state, reservation_id, fingerprint, response_json, tries, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    new_id("att"),
                    fields["job_id"],
                    fields["batch_key"],
                    fields["state"],
                    fields.get("reservation_id"),
                    fields["fingerprint"],
                    fields.get("response_json"),
                    fields.get("tries", 0),
                    now,
                    now,
                ),
            )
            return
        self.execute(
            """
            UPDATE model_attempts
            SET state=?, reservation_id=?, fingerprint=?, response_json=?, tries=?, updated_at=?
            WHERE id=?
            """,
            (
                fields["state"],
                fields.get("reservation_id", current["reservation_id"]),
                fields["fingerprint"],
                fields.get("response_json", current["response_json"]),
                fields.get("tries", current["tries"]),
                now,
                current["id"],
            ),
        )

    def get_scout_cache(self, fingerprint: str) -> str | None:
        row = self.query_one("SELECT response_json FROM scout_cache WHERE fingerprint=?", (fingerprint,))
        return row["response_json"] if row else None

    def put_scout_cache(self, fingerprint: str, response_json: str) -> None:
        self.execute(
            """
            INSERT INTO scout_cache (fingerprint, response_json, created_at) VALUES (?,?,?)
            ON CONFLICT(fingerprint) DO UPDATE SET response_json=excluded.response_json
            """,
            (fingerprint, response_json, utcnow()),
        )

    def get_opportunity_cache(self, fingerprint: str) -> str | None:
        row = self.query_one("SELECT response_json FROM opportunity_cache WHERE fingerprint=?", (fingerprint,))
        return row["response_json"] if row else None

    def put_opportunity_cache(self, fingerprint: str, response_json: str) -> None:
        self.execute(
            """
            INSERT INTO opportunity_cache (fingerprint, response_json, created_at) VALUES (?,?,?)
            ON CONFLICT(fingerprint) DO UPDATE SET response_json=excluded.response_json
            """,
            (fingerprint, response_json, utcnow()),
        )

    def job_open_reserve_usd(self, job_id: str) -> float:
        row = self.query_one(
            """
            SELECT COALESCE(SUM(amount_usd), 0) AS n FROM budget_entries
            WHERE job_id=? AND kind='reserve' AND reservation_id NOT IN (
              SELECT reservation_id FROM budget_entries WHERE kind IN ('reconcile', 'release')
            )
            """,
            (job_id,),
        )
        return float(row["n"]) if row else 0.0

    def job_committed_usd(self, job_id: str) -> float:
        row = self.query_one(
            """
            SELECT COALESCE(SUM(amount_usd), 0) AS n FROM budget_entries
            WHERE job_id=? AND kind='reconcile'
            """,
            (job_id,),
        )
        return float(row["n"]) if row else 0.0
