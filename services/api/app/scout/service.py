"""Start a scout submission and run one claimed analysis. Convex stays the owner of review state."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import subprocess
from pathlib import Path

import cv2

from app.db import Database, new_id, utcnow
from app.scout.pipeline import ClaudeScout, event_payload, run_scout
from app.versions import SCOUT_PROMPT_VERSION, SCOUT_SCHEMA_VERSION

log = logging.getLogger("secondlook.scout")


def grab_jpeg(video: Path, t_ms: int, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{t_ms / 1000:.3f}", "-i", str(video),
            "-frames:v", "1", "-vf", "scale=960:-2,format=yuvj420p", str(dest),
        ],
        check=True,
    )


def _prepare_clip(db: Database, settings, video: dict, t_ms: int) -> dict:
    duration = int(video["duration_ms"])
    end_ms = min(duration, t_ms + settings.scout_max_video_seconds * 1000)
    start_ms = max(0, t_ms - 1000)
    video_path = settings.data_path / video["original_path"]
    manifest_id = new_id("man")
    relative_dir = f"videos/{video['id']}/manifests/{manifest_id}"
    dest = settings.data_path / relative_dir / "f01.jpg"
    grab_jpeg(video_path, t_ms, dest)
    frame = {
        "frame_id": "f01",
        "source_t_ms": t_ms,
        "file": "f01.jpg",
        "relative": f"{relative_dir}/f01.jpg",
    }
    db.insert_manifest(
        {
            "id": manifest_id,
            "video_id": video["id"],
            "start_ms": start_ms,
            "end_ms": end_ms,
            "sampler_version": "scout-v1",
            "frames": [frame],
            "created_at": utcnow(),
        }
    )
    return {"video": video, "t_ms": t_ms, "duration": duration, "start_ms": start_ms, "end_ms": end_ms, "manifest_id": manifest_id}


def start_batch(db: Database, settings, client, *, player_name: str, clips: list[dict]) -> dict:
    """One submission, one window per clip. clips are {video, t_ms, box}."""
    prepared = [_prepare_clip(db, settings, clip["video"], clip["t_ms"]) for clip in clips]
    name = player_name.strip()
    code = secrets.token_urlsafe(9)
    key = new_id("sub")
    player_key = new_id("plr")
    secret = settings.convex_worker_secret
    notes = []
    for item in prepared:
        note = (item["video"].get("rights_note") or "").strip()
        if note and note not in notes:
            notes.append(note)
    client.mutation(
        "worker:createSubmission",
        {
            "secret": secret,
            "key": key,
            "playerKey": player_key,
            "playerName": name,
            "title": f"Scout {name}",
            "accessHash": hashlib.sha256(code.encode()).hexdigest(),
            "rightsNote": "; ".join(notes)[:500] or "Local footage.",
        },
    )
    window_ids = []
    for order, (item, clip) in enumerate(zip(prepared, clips), start=1):
        marks = sorted(clip.get("marks") or [{"t_ms": item["t_ms"], "box": clip["box"]}], key=lambda mark: mark["t_ms"])
        frames = [{"frameId": f"f{index + 1:02d}", "tMs": mark["t_ms"]} for index, mark in enumerate(marks)]
        anchors = [
            {"frameId": f"f{index + 1:02d}", "state": "located", "source": "manual", "box": mark["box"]}
            for index, mark in enumerate(marks)
        ]
        window_id = client.mutation(
            "worker:registerWindow",
            {
                "secret": secret,
                "submissionKey": key,
                "order": order,
                "videoKey": item["video"]["id"],
                "manifestKey": item["manifest_id"],
                "videoDurationMs": item["duration"],
                "startMs": item["start_ms"],
                "endMs": item["end_ms"],
                "frames": frames,
                "linkStatement": f"Marked {len(marks)} times in clip {order} by the person who started this analysis.",
                "assertedBy": name,
                "kind": "scout",
                "initialRevision": {
                    "key": new_id("rev"),
                    "anchors": anchors,
                    "jerseyNote": "",
                    "teamColorNote": "",
                    "note": "",
                },
            },
        )
        window_ids.append(window_id)
    for window_id in window_ids:
        client.mutation("review:queueAnalysis", {"key": key, "code": code, "windowId": window_id, "reviewer": name})
    return {"key": key, "code": code, "window_id": window_ids[0], "window_ids": window_ids}


def start_submission(db: Database, settings, client, *, video: dict, t_ms: int, box: dict, player_name: str) -> dict:
    return start_batch(db, settings, client, player_name=player_name, clips=[{"video": video, "t_ms": t_ms, "box": box}])


def execute(app, client, claim: dict, stop) -> None:
    from app.convex_bridge import ensure_revision
    from app.jobs import model_name

    db: Database = app.state.db
    settings = app.state.settings
    secret = settings.convex_worker_secret
    request_id = claim["requestId"]
    window = claim["window"]
    video = db.get_video(window["videoKey"])
    manifest = db.get_manifest(window["manifestKey"])
    if video is None or manifest is None:
        client.mutation(
            "worker:failRequest",
            {"secret": secret, "requestId": request_id, "errorCode": "missing_input", "errorMessage": "The clip is not on this worker.", "retryable": False},
        )
        return
    video_path = settings.data_path / video["original_path"]
    revision = ensure_revision(db, manifest, claim["revision"])
    job_id = new_id("job")
    now = utcnow()
    db.insert_job(
        {
            "id": job_id,
            "video_id": video["id"],
            "manifest_id": manifest["id"],
            "target_revision_id": revision["id"],
            "status": "running",
            "stage": "tracking",
            "attempts": 1,
            "idempotency_key": f"cvx:{request_id}:{claim['attempt']}",
            "fingerprint": f"scout:{video['sha256']}:{revision['id']}",
            "cache_status": "live",
            "stage_log": [{"stage": "tracking", "at": now}],
            "created_at": now,
            "started_at": now,
        }
    )
    cancelled = {"value": False}

    def progress(info: dict) -> None:
        report = {
            "phase": info.get("phase", "scout"),
            "chunksDone": info.get("chunksDone"),
            "chunksTotal": info.get("chunksTotal"),
            "candidates": info.get("candidates"),
            "trackedMs": info.get("trackedMs"),
            "lostMs": info.get("lostMs"),
            "message": info.get("message"),
        }
        report = {key: value for key, value in report.items() if value is not None}
        result = client.mutation(
            "worker:progress",
            {"secret": secret, "requestId": request_id, "stage": report["phase"], "jobKey": job_id, "progress": report},
        )
        if result and result.get("cancelRequested"):
            cancelled["value"] = True

    def should_stop() -> bool:
        return stop.is_set() or cancelled["value"]

    run_id = client.mutation(
        "worker:openRun",
        {
            "secret": secret,
            "requestId": request_id,
            "runKey": f"scout:{revision['id']}",
            "model": model_name(settings),
            "promptVersion": SCOUT_PROMPT_VERSION,
            "schemaVersion": SCOUT_SCHEMA_VERSION,
        },
    )

    def on_events(found) -> None:
        client.mutation(
            "worker:addObservations",
            {"secret": secret, "runId": run_id, "observations": [event_payload(event, index) for index, event in enumerate(found)]},
        )

    times = {frame["frameId"]: frame["tMs"] for frame in window.get("frames", [])}
    anchors = []
    for anchor in claim["revision"]["anchors"]:
        if anchor.get("state") == "located" and anchor.get("box"):
            box = anchor["box"]
            anchors.append((times.get(anchor["frameId"], window["startMs"]), (box["x"], box["y"], box["w"], box["h"])))
    result = run_scout(
        db, settings,
        video=video_path, sha=video["sha256"], start_ms=window["startMs"], end_ms=window["endMs"],
        anchors=anchors or [(window["startMs"], (0.4, 0.4, 0.05, 0.2))],
        job_id=job_id, tracker=None, model=ClaudeScout(settings),
        progress=progress, stop=should_stop, on_events=on_events,
    )
    _publish_corrections(db, settings, client, secret, request_id, manifest, video_path, result["corrections"], None)
    client.mutation(
        "worker:closeRun",
        {
            "secret": secret,
            "requestId": request_id,
            "runId": run_id,
            "state": result["state"] if result["state"] in {"succeeded", "partial", "cancelled", "failed"} else "partial",
            "note": result["note"],
            "narrative": json.dumps(result.get("narrative") or []),
            "trackedMs": int((result.get("coverage") or {}).get("tracked_ms") or 0),
            "jobKey": job_id,
        },
    )
    try:
        from app.scout.profile import maybe_build_profile

        maybe_build_profile(app, client, request_id, job_id)
    except Exception:
        log.exception("player profile was not built")
    db.execute(
        "UPDATE jobs SET status=?, stage=?, finished_at=? WHERE id=?",
        ("succeeded" if result["state"] == "succeeded" else "failed", result["state"], utcnow(), job_id),
    )


def _publish_corrections(db, settings, client, secret, request_id, manifest, video_path, corrections, tracker=None) -> None:
    frames = list(manifest["frames"])
    for correction in corrections[:2]:
        number = len(frames) + 1
        frame_id = f"f{number:02d}"
        relative = f"videos/{manifest['video_id']}/manifests/{manifest['id']}/{frame_id}.jpg"
        dest = settings.data_path / relative
        try:
            grab_jpeg(video_path, correction.t_ms, dest)
        except subprocess.CalledProcessError:
            log.warning("could not grab a correction frame")
            continue
        image = cv2.imread(str(dest))
        shown = list(correction.boxes)
        if image is not None and tracker is not None:
            detected = tracker.detect_people(image)
            if detected:
                shown = detected
        if image is not None:
            height, width = image.shape[:2]
            for person in shown:
                x, y, w, h = person.box
                cv2.rectangle(image, (int(x * width), int(y * height)), (int((x + w) * width), int((y + h) * height)), (0, 165, 255), 2)
            cv2.imwrite(str(dest), image)
        height, width = (image.shape[:2] if image is not None else (0, 0))
        frames.append({
            "frame_id": frame_id,
            "source_t_ms": correction.t_ms,
            "derivative_t_ms": correction.t_ms,
            "width": width,
            "height": height,
            "file": f"{frame_id}.jpg",
            "relative": relative,
        })
        client.mutation(
            "worker:addCorrection",
            {
                "secret": secret,
                "requestId": request_id,
                "frameId": frame_id,
                "tMs": correction.t_ms,
                "reason": "The track was lost here. Click the selected player to continue.",
                "boxes": [
                    {"trackId": person.track_id, "box": {"x": person.box[0], "y": person.box[1], "w": person.box[2], "h": person.box[3]}, "confidence": person.confidence}
                    for person in shown
                ],
            },
        )
    db.execute("UPDATE manifests SET frames_json=? WHERE id=?", (json.dumps(frames), manifest["id"]))
