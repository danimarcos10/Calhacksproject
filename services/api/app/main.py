import asyncio
import gzip
import hashlib
import json
import logging
import re
import shutil
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import sqlite3
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.anchors import present_anchor, review_reasons
from app.config import Settings
from app.db import Database, new_id, utcnow
from app.schemas import (
    AnalysisOut,
    AnalysisRequest,
    HealthOut,
    JobOut,
    ManifestOut,
    ReadyOut,
    RevisionOut,
    ProposalOut,
    ProposalRequest,
    SampleRequest,
    OpportunityIn,
    OpportunityOut,
    ProgramsIn,
    ProgramsOut,
    ReachIn,
    ReachOut,
    SendIn,
    SendOut,
    FindPlayerIn,
    FindPlayerOut,
    StickIn,
    StickOut,
    ScoutBatchIn,
    ScoutStartIn,
    TargetRequest,
    VideoOut,
)
from app.errors import AppError
from app.media import format_duration_ms, make_playback, probe_video, sample_window
from app.providers.anthropic import AnthropicProvider
from app.providers.synthetic import SyntheticProvider
from app.versions import SAMPLER_VERSION
from app.convex_bridge import bridge_loop
from app.jobs import enqueue_analysis
from app.worker import worker_loop

log = logging.getLogger("secondlook")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

_ID = re.compile(r"^(vid|man|rev|job|run)_[0-9a-f]{16}$")


def build_provider(settings: Settings):
    mode = settings.evidence_provider.strip().lower()
    if mode == "synthetic":
        return SyntheticProvider()
    if mode != "anthropic":
        raise RuntimeError("EVIDENCE_PROVIDER must be anthropic or synthetic")
    if not settings.anthropic_api_key.strip():
        return None
    return AnthropicProvider(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
        timeout=settings.provider_timeout_seconds,
        max_output_tokens=settings.max_output_tokens,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.data_path.mkdir(parents=True, exist_ok=True)
        (settings.data_path / "logs").mkdir(exist_ok=True)
        app.state.db = Database(settings.db_path)
        app.state.db.mark_interrupted()
        app.state.provider = build_provider(settings)
        stop = threading.Event()
        thread = threading.Thread(target=worker_loop, args=(app, stop), name="secondlook-worker", daemon=True)
        thread.start()
        bridge = None
        if settings.convex_url.strip() and settings.convex_worker_secret.strip():
            bridge = threading.Thread(target=bridge_loop, args=(app, stop), name="secondlook-convex", daemon=True)
            bridge.start()
        yield
        stop.set()
        thread.join(timeout=2)
        if bridge:
            bridge.join(timeout=2)
        app.state.db.close()

    app = FastAPI(title="SecondLook", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.provider_cache = None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.app_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Accept-Ranges", "Content-Range", "Content-Length", "X-Request-Id"],
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = "req_" + uuid.uuid4().hex[:12]
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @app.exception_handler(AppError)
    async def app_error(_request: Request, exc: AppError):
        return JSONResponse(_envelope(exc.code, exc.user_message, exc.retryable, _request), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def invalid(_request: Request, exc: RequestValidationError):
        field = ""
        if exc.errors():
            parts = [str(part) for part in exc.errors()[0].get("loc", []) if part != "body"]
            field = ".".join(parts)
        message = f"Check the {field} field and try again." if field else "The request had an invalid value."
        return JSONResponse(_envelope("invalid_request", message, False, _request), status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception):
        log.error("request failed type=%s", type(exc).__name__)
        return JSONResponse(
            _envelope("internal_error", "Something went wrong on the server. Retry this step.", True, _request),
            status_code=500,
        )

    @app.get("/healthz", response_model=HealthOut)
    def healthz():
        return {"status": "ok"}

    @app.get("/readyz", response_model=ReadyOut)
    def readyz(request: Request):
        ffmpeg_ok = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
        writable = _writable(settings.data_path)
        provider = _provider_status(request.app)
        ready = ffmpeg_ok and writable
        body = {
            "status": "ready" if ready else "not_ready",
            "ffmpeg": ffmpeg_ok,
            "data_dir_writable": writable,
            "provider": provider,
        }
        return JSONResponse(body, status_code=200 if ready else 503)

    @app.post("/api/videos", status_code=201, response_model=VideoOut)
    async def create_video(request: Request, file: UploadFile = File(...), rights_note: str = Form("")):
        db: Database = request.app.state.db
        name = Path(file.filename or "").name
        suffix = Path(name).suffix.lower()
        if suffix not in {".mp4", ".mov"}:
            raise AppError("unsupported_type", "Upload an MP4 or MOV file.", 400)
        incoming = settings.data_path / "incoming" / f"{uuid.uuid4().hex}.bin"
        folder: Path | None = None
        try:
            _size, digest = await _save_upload(file, incoming, settings.max_upload_mb * 1024 * 1024, settings.max_upload_mb)
            probe = await asyncio.to_thread(
                probe_video,
                incoming,
                min_seconds=settings.min_video_seconds,
                max_seconds=max(settings.max_video_seconds, settings.scout_max_video_seconds),
            )
            video_id = new_id("vid")
            folder = settings.data_path / "videos" / video_id
            folder.mkdir(parents=True, exist_ok=True)
            original_rel = f"videos/{video_id}/original{suffix}"
            playback_rel = f"videos/{video_id}/playback.mp4"
            original = settings.data_path / original_rel
            incoming.replace(original)
            incoming = None
            await asyncio.to_thread(make_playback, original, settings.data_path / playback_rel)
            duration_ms = await asyncio.to_thread(format_duration_ms, settings.data_path / playback_rel)
            db.insert_video(
                {
                    "id": video_id,
                    "sha256": digest,
                    "original_path": original_rel,
                    "playback_path": playback_rel,
                    "duration_ms": duration_ms,
                    "timeline_ms": probe.timeline_ms,
                    "width": probe.display_width,
                    "height": probe.display_height,
                    "rotation": probe.rotation,
                    "codec": probe.codec,
                    "frame_rate": probe.frame_rate,
                    "first_pts": probe.first_pts,
                    "metadata": {
                        "coded_width": probe.coded_width,
                        "coded_height": probe.coded_height,
                        "frame_count": probe.frame_count,
                        "format_name": probe.format_name,
                        "source_duration_ms": probe.duration_ms,
                    },
                    "rights_note": rights_note.strip()[:200],
                    "created_at": utcnow(),
                }
            )
            from app.scout.roboflow import start_tracking

            start_tracking(request.app, video_id)
        except AppError:
            _cleanup(incoming, folder if "original" not in locals() else None)
            if incoming is None and folder and not db.get_video(locals().get("video_id", "")):
                shutil.rmtree(folder, ignore_errors=True)
            raise
        except Exception:
            log.exception("upload failed")
            if incoming is not None and incoming.exists():
                incoming.unlink()
            if folder is not None and folder.exists() and ("video_id" not in locals() or db.get_video(video_id) is None):
                shutil.rmtree(folder, ignore_errors=True)
            raise AppError("internal_error", "The upload could not be processed. Export the clip again.", 400) from None
        return _video_payload(db, video_id)

    @app.get("/api/videos/{video_id}", response_model=VideoOut)
    def get_video(video_id: str, request: Request):
        _require_id(video_id, "vid")
        if request.app.state.db.get_video(video_id) is None:
            raise AppError("not_found", "That clip was not found.", 404)
        return _video_payload(request.app.state.db, video_id)

    @app.get("/api/videos/{video_id}/people")
    def people(video_id: str, t: int, request: Request):
        _require_id(video_id, "vid")
        video = request.app.state.db.get_video(video_id)
        if video is None:
            raise AppError("not_found", "That clip was not found.", 404)
        if t < 0 or t > int(video["duration_ms"]):
            raise AppError("window_outside", "That time is outside the clip.", 400)
        dest = settings.data_path / "tmp" / f"{video_id}-{t}.jpg"
        try:
            from app.scout.service import grab_jpeg
            from app.scout.yolo_tracker import YoloTracker

            grab_jpeg(_under(settings.data_path, video["original_path"]), t, dest)
            tracker = getattr(request.app.state, "yolo", None)
            if tracker is None:
                tracker = YoloTracker()
                request.app.state.yolo = tracker
            import cv2

            image = cv2.imread(str(dest))
            if image is None:
                raise AppError("internal_error", "That frame could not be read.", 400)
            found = tracker.detect_people(image)
        except AppError:
            raise
        except Exception as exc:
            log.warning("people detection unavailable type=%s", type(exc).__name__)
            raise AppError("tracker_unavailable", "Automatic player detection is not available. Draw one box instead.", 503) from None
        return {
            "t_ms": t,
            "people": [{"box": {"x": person.box[0], "y": person.box[1], "w": person.box[2], "h": person.box[3]}, "confidence": person.confidence} for person in found],
        }

    @app.post("/api/videos/{video_id}/scout", status_code=201)
    def start_scout(video_id: str, parsed: ScoutStartIn, request: Request):
        _require_id(video_id, "vid")
        db: Database = request.app.state.db
        video = db.get_video(video_id)
        if video is None:
            raise AppError("not_found", "That clip was not found.", 404)
        if parsed.t_ms > int(video["duration_ms"]):
            raise AppError("window_outside", "That time is outside the clip.", 400)
        if not settings.convex_url or not settings.convex_worker_secret:
            raise AppError("provider_not_configured", "The review service is not connected on this worker.", 503)
        from app.convex_bridge import make_client
        from app.scout.roboflow import read_progress
        from app.scout.service import start_submission

        progress = read_progress(settings.data_path, video["sha256"])
        if progress.get("state") != "succeeded":
            raise AppError("tracker_unavailable", "Player tracking is still running. Wait until the boxes appear, then click the player.", 409)

        try:
            started = start_submission(
                db,
                settings,
                make_client(settings.convex_url),
                video=video,
                t_ms=parsed.t_ms,
                box=parsed.box.model_dump(),
                player_name=parsed.player_name,
            )
        except Exception as exc:
            log.warning("scout start failed type=%s", type(exc).__name__)
            raise AppError("internal_error", "The scouting review could not be opened. Try again.", 400) from None
        return started

    @app.post("/api/scout", status_code=201)
    def start_scout_batch(parsed: ScoutBatchIn, request: Request):
        if len(parsed.clips) > settings.scout_max_clips:
            raise AppError("invalid_request", f"Choose at most {settings.scout_max_clips} clips.", 400)
        if not settings.convex_url or not settings.convex_worker_secret:
            raise AppError("provider_not_configured", "The review service is not connected on this worker.", 503)
        db: Database = request.app.state.db
        from app.convex_bridge import make_client
        from app.scout.roboflow import read_progress
        from app.scout.service import start_batch

        prepared = []
        for clip in parsed.clips:
            _require_id(clip.video_id, "vid")
            video = db.get_video(clip.video_id)
            if video is None:
                raise AppError("not_found", "One of those clips was not found.", 404)
            duration = int(video["duration_ms"])
            marks = [{"t_ms": mark.t_ms, "box": mark.box.model_dump()} for mark in clip.marks]
            if not marks:
                marks = [{"t_ms": clip.t_ms, "box": clip.box.model_dump()}]
            if any(mark["t_ms"] > duration for mark in marks):
                raise AppError("window_outside", "A click is outside its clip.", 400)
            progress = read_progress(settings.data_path, video["sha256"])
            if progress.get("state") != "succeeded":
                raise AppError("tracker_unavailable", "Player tracking is still running on one of the clips.", 409)
            marks.sort(key=lambda mark: mark["t_ms"])
            prepared.append({"video": video, "t_ms": marks[0]["t_ms"], "box": marks[0]["box"], "marks": marks})
        try:
            return start_batch(
                db,
                settings,
                make_client(settings.convex_url),
                player_name=parsed.player_name,
                clips=prepared,
            )
        except Exception as exc:
            log.warning("scout batch failed type=%s", type(exc).__name__)
            raise AppError("internal_error", "The scouting review could not be opened. Try again.", 400) from None

    @app.post("/api/videos/{video_id}/find-player", response_model=FindPlayerOut)
    def find_player(video_id: str, parsed: FindPlayerIn, request: Request):
        _require_id(video_id, "vid")
        db: Database = request.app.state.db
        video = db.get_video(video_id)
        if video is None:
            raise AppError("not_found", "That clip was not found.", 404)
        from app.scout.describe import locate_player
        from app.scout.roboflow import load_tracks, read_progress

        if read_progress(settings.data_path, video["sha256"]).get("state") != "succeeded":
            raise AppError("tracker_unavailable", "Player tracking has not finished for this clip.", 409)
        document = load_tracks(settings.data_path, video["sha256"])
        if document is None:
            raise AppError("tracker_unavailable", "Player tracking has not finished for this clip.", 409)
        return locate_player(settings, settings.data_path / video["original_path"], document["frames"], parsed.description)

    @app.post("/api/videos/{video_id}/stick", response_model=StickOut)
    def stick_player(video_id: str, parsed: StickIn, request: Request):
        _require_id(video_id, "vid")
        video = request.app.state.db.get_video(video_id)
        if video is None:
            raise AppError("not_found", "That clip was not found.", 404)
        if parsed.t_ms > int(video["duration_ms"]):
            raise AppError("window_outside", "That time is outside the clip.", 400)
        from app.scout.goal import scorer_path
        from app.scout.roboflow import load_tracks

        document = load_tracks(settings.data_path, video["sha256"])
        if document is None:
            raise AppError("tracker_unavailable", "Player tracking has not finished for this clip.", 409)
        path = scorer_path(document["frames"], parsed.t_ms, (parsed.box.x, parsed.box.y, parsed.box.w, parsed.box.h))
        span = path[-1]["t"] - path[0]["t"] if len(path) >= 2 else 0
        if span < 800:
            return {"frames": path, "message": "Nobody near the goal stayed with the ball. Click yourself again in the moment the ring is on you."}
        return {"frames": path, "message": f"Locked to your click. Following the player nearest the goal and the ball for {span / 1000:.1f}s. Check the ring."}

    @app.post("/api/reviews/{review_id}/programs", response_model=ProgramsOut)
    def programs(review_id: str, parsed: ProgramsIn, request: Request):
        from app.opportunities import list_programs

        return list_programs(request.app.state.db, settings, review_id, parsed)

    @app.post("/api/reviews/{review_id}/opportunities", response_model=OpportunityOut)
    def opportunities(review_id: str, parsed: OpportunityIn, request: Request):
        from app.opportunities import find_coaches

        return find_coaches(request.app.state.db, settings, review_id, parsed)

    @app.post("/api/reviews/{review_id}/outreach", response_model=SendOut)
    def outreach(review_id: str, parsed: SendIn, request: Request):
        from app.opportunities import send_outreach

        return send_outreach(request.app.state.db, settings, review_id, parsed)

    @app.post("/api/reviews/{review_id}/reach-plan", response_model=ReachOut)
    def reach(review_id: str, parsed: ReachIn, request: Request):
        from app.opportunities import reach_plan

        return reach_plan(request.app.state.db, settings, review_id, parsed)

    @app.get("/api/videos/{video_id}/media")
    def media(video_id: str, request: Request):
        _require_id(video_id, "vid")
        video = request.app.state.db.get_video(video_id)
        if video is None:
            raise AppError("not_found", "That clip was not found.", 404)
        return _ranged(request, _under(settings.data_path, video["playback_path"]), "video/mp4")

    @app.get("/api/videos/{video_id}/tracks")
    def tracks(video_id: str, request: Request):
        _require_id(video_id, "vid")
        video = request.app.state.db.get_video(video_id)
        if video is None:
            raise AppError("not_found", "That clip was not found.", 404)
        from app.scout.roboflow import load_tracks

        document = load_tracks(settings.data_path, video["sha256"])
        if document is None:
            raise AppError("not_found", "Player tracking has not finished for this clip.", 404)
        payload = gzip.compress(json.dumps(document).encode())
        return Response(content=payload, media_type="application/json", headers={"Content-Encoding": "gzip"})

    @app.post("/api/videos/{video_id}/samples", response_model=ManifestOut)
    async def samples(video_id: str, parsed: SampleRequest, request: Request):
        _require_id(video_id, "vid")
        db: Database = request.app.state.db
        video = db.get_video(video_id)
        if video is None:
            raise AppError("not_found", "That clip was not found.", 404)
        length = parsed.end_ms - parsed.start_ms
        minimum = settings.min_window_seconds * 1000
        maximum = settings.max_window_seconds * 1000
        if length < minimum or length > maximum:
            raise AppError(
                "window_length",
                f"Choose a window between {settings.min_window_seconds} and {settings.max_window_seconds} seconds.",
                400,
            )
        if parsed.end_ms > int(video["duration_ms"]) + 50:
            raise AppError("window_outside", "That window extends past the end of the clip.", 400)
        manifest_id = new_id("man")
        relative_dir = f"videos/{video_id}/manifests/{manifest_id}"
        dest = settings.data_path / relative_dir
        cap = min(settings.sample_frame_cap, settings.max_frames_per_call)
        try:
            frames = await asyncio.to_thread(
                sample_window,
                _under(settings.data_path, video["original_path"]),
                dest,
                parsed.start_ms,
                parsed.end_ms,
                cap,
            )
        except AppError:
            shutil.rmtree(dest, ignore_errors=True)
            raise
        for frame in frames:
            frame["relative"] = f"{relative_dir}/{frame['file']}"
        db.insert_manifest(
            {
                "id": manifest_id,
                "video_id": video_id,
                "start_ms": parsed.start_ms,
                "end_ms": parsed.end_ms,
                "sampler_version": SAMPLER_VERSION,
                "frames": frames,
                "created_at": utcnow(),
            }
        )
        return _manifest_payload(db.get_manifest(manifest_id))

    @app.get("/api/videos/{video_id}/frames/{frame_id}")
    def frame(video_id: str, frame_id: str, manifest: str, request: Request):
        _require_id(video_id, "vid")
        _require_id(manifest, "man")
        if not re.fullmatch(r"f\d{2}", frame_id):
            raise AppError("not_found", "That frame was not found.", 404)
        row = request.app.state.db.get_manifest(manifest)
        if row is None or row["video_id"] != video_id:
            raise AppError("not_found", "That frame was not found.", 404)
        match = next((item for item in row["frames"] if item["frame_id"] == frame_id), None)
        if match is None:
            raise AppError("not_found", "That frame was not found.", 404)
        path = _under(settings.data_path, match["relative"])
        return Response(path.read_bytes(), media_type="image/jpeg")

    @app.post("/api/videos/{video_id}/targets", response_model=RevisionOut)
    def targets(video_id: str, parsed: TargetRequest, request: Request):
        _require_id(video_id, "vid")
        db: Database = request.app.state.db
        if db.get_video(video_id) is None:
            raise AppError("not_found", "That clip was not found.", 404)
        manifest = db.get_manifest(parsed.manifest_id)
        if manifest is None or manifest["video_id"] != video_id:
            raise AppError("unknown_manifest", "Sample a window on this clip before marking the target.", 400)
        if db.attachment(manifest["id"]):
            raise AppError(
                "window_in_submission",
                "This window belongs to a submission. Edit the player selection from the submission's Prepare page.",
                409,
            )
        known = {frame["frame_id"] for frame in manifest["frames"]}
        anchors = [anchor.model_dump() for anchor in parsed.anchors]
        if any(anchor["frame_id"] not in known for anchor in anchors):
            raise AppError("unknown_frame", "An anchor refers to a frame that is not in this window.", 400)
        if len({anchor["frame_id"] for anchor in anchors}) != len(anchors):
            raise AppError("duplicate_anchor", "Each frame can have only one anchor.", 400)
        if not any(anchor["state"] == "located" for anchor in anchors):
            raise AppError("anchor_required", "Mark the target on at least one frame, or choose another window.", 400)
        revision_id = new_id("rev")
        try:
            with db.transaction():
                number = db.next_revision_number(video_id)
                db.insert_revision(
                    {
                        "id": revision_id,
                        "video_id": video_id,
                        "manifest_id": manifest["id"],
                        "revision": number,
                        "anchors": anchors,
                        "jersey_note": parsed.jersey_note.strip(),
                        "team_color_note": parsed.team_color_note.strip(),
                        "identity_uncertain": False,
                        "role": parsed.role.strip(),
                        "note": parsed.note.strip(),
                        "created_at": utcnow(),
                    }
                )
        except sqlite3.IntegrityError as exc:
            raise AppError("revision_conflict", "The target was saved by another request. Load it again.", 409, True) from exc
        return _revision_payload(db.get_revision(revision_id))

    @app.post("/api/videos/{video_id}/proposals", response_model=ProposalOut)
    def proposals(video_id: str, parsed: ProposalRequest, request: Request):
        _require_id(video_id, "vid")
        db: Database = request.app.state.db
        video = db.get_video(video_id)
        if video is None:
            raise AppError("not_found", "That clip was not found.", 404)
        manifest = db.get_manifest(parsed.manifest_id)
        if manifest is None or manifest["video_id"] != video_id:
            raise AppError("unknown_manifest", "Sample a window on this clip before proposing locations.", 400)
        try:
            from app.propagate import decode_window, proposals_for_frames
        except ImportError as exc:
            raise AppError("tracker_unavailable", "Location proposals are not available on this machine.", 503) from exc
        work = settings.data_path / "proposals" / video_id
        try:
            frames, times = decode_window(
                _under(settings.data_path, video["original_path"]),
                manifest["start_ms"],
                manifest["end_ms"],
                work,
            )
            proposed = proposals_for_frames(
                frames,
                times,
                [{"frame_id": frame["frame_id"], "source_t_ms": frame["source_t_ms"]} for frame in manifest["frames"]],
                [anchor.model_dump() for anchor in parsed.anchors],
            )
        except (RuntimeError, ImportError, OSError) as exc:
            raise AppError("tracker_failed", "Locations could not be proposed for this window. Mark the frames manually.", 500, True) from exc
        return {"anchors": proposed}

    @app.post("/api/analyses", response_model=JobOut)
    def analyses(parsed: AnalysisRequest, request: Request):
        _require_id(parsed.video_id, "vid")
        _require_id(parsed.manifest_id, "man")
        _require_id(parsed.target_revision_id, "rev")
        db: Database = request.app.state.db
        mode = settings.evidence_provider.strip().lower()
        if mode == "anthropic" and not settings.anthropic_api_key.strip():
            raise AppError(
                "provider_not_configured",
                "Add ANTHROPIC_API_KEY on the server to run analysis. The upload and target are saved.",
                400,
            )
        key = request.headers.get("idempotency-key")
        if key:
            key = key.strip()[:80]
            existing = db.job_by_idempotency(key)
            if existing:
                return _job_payload(db, existing)
        video = db.get_video(parsed.video_id)
        manifest = db.get_manifest(parsed.manifest_id)
        revision = db.get_revision(parsed.target_revision_id)
        if video is None or manifest is None or revision is None:
            raise AppError("not_found", "That clip or target was not found.", 404)
        if manifest["video_id"] != video["id"] or revision["video_id"] != video["id"]:
            raise AppError("not_found", "That target does not belong to this clip.", 404)
        if revision["manifest_id"] != manifest["id"]:
            raise AppError("stale_window", "The target was marked on a different window. Mark it again.", 400)
        if db.attachment(manifest["id"]):
            raise AppError(
                "window_in_submission",
                "This window belongs to a submission. Queue it from the submission's review page.",
                409,
            )
        return _job_payload(db, enqueue_analysis(db, settings, video, manifest, revision, key))

    @app.get("/api/jobs/{job_id}", response_model=JobOut)
    def job(job_id: str, request: Request):
        _require_id(job_id, "job")
        row = request.app.state.db.get_job(job_id)
        if row is None:
            raise AppError("not_found", "That analysis job was not found.", 404)
        return _job_payload(request.app.state.db, row)

    @app.get("/api/analyses/{run_id}", response_model=AnalysisOut)
    def analysis(run_id: str, request: Request):
        _require_id(run_id, "run")
        payload = _analysis_payload(request.app.state.db, run_id, None)
        if payload is None:
            raise AppError("not_found", "That analysis was not found.", 404)
        return payload

    return app


def _envelope(code: str, message: str, retryable: bool, request: Request) -> dict:
    return {
        "code": code,
        "user_message": message,
        "retryable": retryable,
        "request_id": getattr(request.state, "request_id", None),
    }


def _require_id(value: str, prefix: str) -> None:
    if not _ID.fullmatch(value) or not value.startswith(prefix + "_"):
        raise AppError("not_found", "That record was not found.", 404)


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _provider_status(app: FastAPI) -> dict:
    settings: Settings = app.state.settings
    mode = settings.evidence_provider.strip().lower()
    cached = app.state.provider_cache
    now = time.monotonic()
    if cached and now - cached["at"] < 60:
        return cached["body"]
    if mode == "synthetic":
        body = {
            "mode": "synthetic",
            "configured": True,
            "model": "synthetic-fixture",
            "reachable": False,
            "detail": "Synthetic fixture provider is on. Results are not football analysis.",
        }
    elif not settings.anthropic_api_key.strip():
        body = {
            "mode": "anthropic",
            "configured": False,
            "model": settings.anthropic_model,
            "reachable": False,
            "detail": "ANTHROPIC_API_KEY is not set. Upload and selection still work.",
        }
    else:
        body = _check_model(settings)
    app.state.provider_cache = {"at": now, "body": body}
    return body


def _check_model(settings: Settings) -> dict:
    import anthropic

    base = {
        "mode": "anthropic",
        "configured": True,
        "model": settings.anthropic_model,
        "reachable": False,
        "detail": "The model service could not be checked.",
    }
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=15, max_retries=0)
        model = client.models.retrieve(settings.anthropic_model)
        return {**base, "model": model.id, "reachable": True, "detail": "Model is reachable."}
    except anthropic.AuthenticationError:
        return {**base, "detail": "The API key was rejected."}
    except anthropic.NotFoundError:
        return {**base, "detail": "The configured model was not found on this account."}
    except Exception:
        log.info("provider check failed type=%s", "error")
        return base


def _under(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        raise AppError("not_found", "That file was not found.", 404)
    if not path.is_file():
        raise AppError("not_found", "That file was not found.", 404)
    return path


def _cleanup(incoming: Path | None, folder: Path | None) -> None:
    if incoming is not None and incoming.exists():
        incoming.unlink()
    if folder is not None and folder.exists():
        shutil.rmtree(folder, ignore_errors=True)


async def _save_upload(upload: UploadFile, dest: Path, max_bytes: int, max_mb: int) -> tuple[int, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    size = 0
    with dest.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                handle.close()
                dest.unlink(missing_ok=True)
                raise AppError("upload_too_large", f"Uploads are limited to {max_mb} MB.", 413)
            hasher.update(chunk)
            handle.write(chunk)
    if size == 0:
        dest.unlink(missing_ok=True)
        raise AppError("empty_upload", "The file was empty.", 400)
    return size, hasher.hexdigest()


def _ranged(request: Request, path: Path, media_type: str) -> Response:
    size = path.stat().st_size
    header = request.headers.get("range")
    if not header:
        return StreamingResponse(
            _chunks(path, 0, size),
            media_type=media_type,
            headers={"Accept-Ranges": "bytes", "Content-Length": str(size)},
        )
    match = re.fullmatch(r"bytes=(\d+)-(\d*)", header.strip())
    if not match:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else size - 1
    end = min(end, size - 1)
    if start > end or start >= size:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    length = end - start + 1
    return StreamingResponse(
        _chunks(path, start, length),
        status_code=206,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(length),
        },
    )


def _chunks(path: Path, start: int, length: int):
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining:
            chunk = handle.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _video_payload(db: Database, video_id: str) -> dict:
    video = db.get_video(video_id)
    return {
        "id": video["id"],
        "duration_ms": video["duration_ms"],
        "timeline_ms": video["timeline_ms"],
        "width": video["width"],
        "height": video["height"],
        "rotation": video["rotation"],
        "codec": video["codec"],
        "media_url": f"/api/videos/{video['id']}/media",
        "rights_note": video["rights_note"],
        "manifests": [_manifest_payload(row) for row in db.manifests_for_video(video_id)],
        "revisions": [_revision_payload(row) for row in db.revisions_for_video(video_id)],
        "tracking": _tracking_payload(db, video),
    }


def _tracking_payload(db: Database, video: dict) -> dict:
    del db
    from app.config import Settings
    from app.scout.roboflow import read_progress

    return read_progress(Settings().data_path, video["sha256"])


def _manifest_payload(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "video_id": row["video_id"],
        "start_ms": row["start_ms"],
        "end_ms": row["end_ms"],
        "sampler_version": row["sampler_version"],
        "frames": [
            {
                "frame_id": frame["frame_id"],
                "source_t_ms": frame["source_t_ms"],
                "derivative_t_ms": frame.get("derivative_t_ms", frame["source_t_ms"]),
                "width": frame.get("width") or 0,
                "height": frame.get("height") or 0,
                "url": f"/api/videos/{row['video_id']}/frames/{frame['frame_id']}?manifest={row['id']}",
            }
            for frame in row["frames"]
        ],
    }


def _revision_payload(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "video_id": row["video_id"],
        "manifest_id": row["manifest_id"],
        "revision": row["revision"],
        "anchors": [present_anchor(anchor) for anchor in row["anchors"]],
        "jersey_note": row["jersey_note"],
        "team_color_note": row["team_color_note"],
        "identity_uncertain": row["identity_uncertain"],
        "role": row["role"] or "",
        "note": row.get("note") or "",
        "needs_review": review_reasons(row["anchors"], bool(row["identity_uncertain"])),
        "created_at": row["created_at"],
    }


def _job_payload(db: Database, job: dict) -> dict:
    result = None
    if job.get("result_run_id"):
        result = _analysis_payload(db, job["result_run_id"], job.get("cache_status"))
    error = None
    if job.get("error_code"):
        error = {
            "code": job["error_code"],
            "user_message": job["error_message"],
            "retryable": bool(job.get("error_retryable")),
        }
    return {
        "id": job["id"],
        "video_id": job["video_id"],
        "status": job["status"],
        "stage": job["stage"],
        "stage_log": job["stage_log"],
        "attempts": job["attempts"],
        "cache_status": job["cache_status"],
        "error": error,
        "result_run_id": job.get("result_run_id"),
        "result": result,
        "timings": {
            "created_at": job["created_at"],
            "started_at": job["started_at"],
            "finished_at": job["finished_at"],
        },
    }


def _analysis_payload(db: Database, run_id: str, cache_status: str | None) -> dict | None:
    run = db.get_run(run_id)
    if run is None:
        return None
    revision = db.get_revision(run["target_revision_id"])
    manifest = db.get_manifest(run["manifest_id"])
    return {
        "id": run["id"],
        "video_id": run["video_id"],
        "target_revision": revision["revision"] if revision else None,
        "target_revision_id": run["target_revision_id"],
        "window": {"start_ms": manifest["start_ms"], "end_ms": manifest["end_ms"]} if manifest else None,
        "status": run["status"],
        "observations": [
            {
                "id": item["id"],
                "category": item["category"],
                "start_ms": item["start_ms"],
                "end_ms": item["end_ms"],
                "frame_ids": item["frame_ids"],
                "visible_action": item["visible_action"],
                "outcome": item["outcome"],
                "evidence_status": item["evidence_status"],
                "identity_status": item["identity_status"],
                "limitations": item["limitations"],
                "continuity_issues": item.get("continuity_issues") or [],
                "seek_ms": item.get("seek_ms", item["start_ms"]),
                "review_status": item["review_status"],
                "attribution_hold": item["attribution_hold"],
                "hold_reason": item.get("hold_reason") or "",
                "hold_frame_id": item.get("hold_frame_id"),
            }
            for item in db.observations_for_run(run_id)
        ],
        "gaps": run["gaps"],
        "validation_issues": run["issues"],
        "resample_request": run["resample"],
        "no_observation_reason": run["no_observation_reason"],
        "provenance": {
            "model_requested": run["model_requested"],
            "model_returned": run["model_returned"],
            "prompt_version": run["prompt_version"],
            "schema_version": run["schema_version"],
            "sampler_version": run["sampler_version"],
            "usage": run["usage"],
            "cost_usd": run["cost_usd"],
            "latency_ms": run["latency_ms"],
            "stop_reason": run["stop_reason"],
            "request_id": run["request_id"],
            "provider_label": run["provider_label"],
            "cache_status": cache_status or "live",
            "created_at": run["created_at"],
        },
    }


app = create_app()
