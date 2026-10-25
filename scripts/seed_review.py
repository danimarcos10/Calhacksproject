"""Create the demo submissions in Convex from clips already stored by the API.

Idempotent. Review codes, submission keys and sampled manifest ids are kept in
data/review_seed_state.json (gitignored) so a rerun reuses them. Windows that name
a start and end are sampled through the running API. A window whose manifest already
has a saved player selection imports it as selection 1, keeping estimated boxes
labelled as estimated.

Run from the repository root with the API running and Convex configured:
    services/api/.venv/Scripts/python scripts/seed_review.py
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

import httpx  # noqa: E402
from convex import ConvexClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.db import Database, new_id  # noqa: E402
from app.publish import anchor_to_convex  # noqa: E402

SPEC = ROOT / "scripts" / "review_seed.json"


def main() -> int:
    settings = Settings()
    if not settings.convex_url or not settings.convex_worker_secret:
        print("Run scripts/convex_setup.py first.")
        return 1
    state_path = settings.data_path / "review_seed_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    db = Database(settings.db_path)
    client = ConvexClient(settings.convex_url)
    secret = settings.convex_worker_secret
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    links = []

    for item in spec["submissions"]:
        entry = state.setdefault(item["slug"], {})
        entry.setdefault("key", new_id("sub"))
        entry.setdefault("code", secrets.token_urlsafe(9))
        entry.setdefault("manifests", {})
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        client.mutation(
            "worker:createSubmission",
            {
                "secret": secret,
                "key": entry["key"],
                "playerKey": item["player"]["key"],
                "playerName": item["player"]["name"],
                "title": item["title"],
                "accessHash": hashlib.sha256(entry["code"].encode()).hexdigest(),
                "rightsNote": item["rights"],
            },
        )
        for order, window in enumerate(item["windows"], start=1):
            video = db.get_video(window["video"])
            if video is None:
                print(f"{item['slug']}: clip {window['video']} is not stored. Upload it first.")
                return 1
            manifest_id = window.get("manifest") or entry["manifests"].get(str(order))
            if not manifest_id:
                response = httpx.post(
                    f"{settings.api_origin.rstrip('/')}/api/videos/{video['id']}/samples",
                    json={"start_ms": window["start_ms"], "end_ms": window["end_ms"]},
                    timeout=120,
                )
                response.raise_for_status()
                manifest_id = response.json()["id"]
                entry["manifests"][str(order)] = manifest_id
                state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            manifest = db.get_manifest(manifest_id)
            revision = db.latest_revision_for_manifest(manifest_id)
            body = {
                "secret": secret,
                "submissionKey": entry["key"],
                "order": order,
                "videoKey": video["id"],
                "manifestKey": manifest_id,
                "videoDurationMs": int(video["duration_ms"]),
                "startMs": manifest["start_ms"],
                "endMs": manifest["end_ms"],
                "frames": [{"frameId": f["frame_id"], "tMs": int(f["source_t_ms"])} for f in manifest["frames"]],
                "linkStatement": item["link"],
                "assertedBy": "Uploader (seed)",
            }
            if revision:
                body["initialRevision"] = {
                    "key": revision["id"],
                    "anchors": [anchor_to_convex(a) for a in revision["anchors"]],
                    "jerseyNote": revision.get("jersey_note") or "",
                    "teamColorNote": revision.get("team_color_note") or "",
                    "note": revision.get("note") or "",
                }
            client.mutation("worker:registerWindow", body)
            db.attach_manifest(manifest_id, entry["key"])
        links.append((item["title"], f"{settings.app_origin.rstrip('/')}/review/{entry['key']}?code={entry['code']}"))

    print("Review links (local demo; each code opens one submission):")
    for title, link in links:
        print(f"  {title}: {link}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
