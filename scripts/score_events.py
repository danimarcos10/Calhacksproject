"""Score possession events against SoccerTrack ball-action labels.

The labels are bas/118577. A pass counts when a predicted pass or receive
falls within one second of a PASS, HIGH PASS, or CROSS. The script stops
when the panorama was not tracked: that clip missed the player gate and
is too slow to track inside this session.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = Path.home() / ".cache" / "huggingface" / "hub"
PASS_LABELS = {"PASS", "HIGH PASS", "CROSS"}
WINDOW_MS = 1000


def label_times(path: Path, end_ms: int = 180_000) -> list[int]:
    document = json.loads(path.read_text(encoding="utf-8"))
    times = []
    for action in document["actions"]:
        if action.get("label") not in PASS_LABELS:
            continue
        frame = int(action["frame"])
        fps = float(document.get("fps") or 25)
        t_ms = int(round(frame / fps * 1000))
        if 0 <= t_ms <= end_ms:
            times.append(t_ms)
    return times


def predicted_times(tracks_path: Path, end_ms: int = 180_000) -> list[int]:
    from app.scout.possession import events_for

    document = json.loads(tracks_path.read_text(encoding="utf-8"))
    frames = [frame for frame in document["frames"] if frame["t"] <= end_ms]
    identity = set()
    for frame in frames:
        for player in frame["players"]:
            if player["cls"] != 3:
                identity.add(int(player["id"]))
    events = events_for(frames, identity)
    return [event.start_ms for event in events if event.action in {"pass", "receive"} and event.start_ms <= end_ms]


def match(predicted: list[int], labels: list[int]) -> tuple[int, int, int]:
    used = set()
    hits = 0
    for guess in predicted:
        for index, truth in enumerate(labels):
            if index in used:
                continue
            if abs(guess - truth) <= WINDOW_MS:
                used.add(index)
                hits += 1
                break
    return hits, len(predicted), len(labels)


def main() -> int:
    label_files = list(LABELS.glob("datasets--atomscott--soccertrack-v2/**/bas/118577/118577_12_class_events.json"))
    track_files = list((ROOT / "data" / "tracks").glob("*/roboflow-sports-1/tracks.json"))
    soccer = [path for path in track_files if "118577" in path.read_text(encoding="utf-8")[:200]]
    if not label_files:
        print("cut: bas/118577 was not downloaded, so precision and recall were not computed.")
        return 0
    if not soccer:
        print(
            "cut: SoccerTrack 118577 was measured at 12.6 players per frame and 5800 ms per frame. "
            "It missed the 18-player gate, so the broadcast clip is the demo. "
            "A 180 second track at that rate is about three hours, so events were not produced and precision and recall were not computed. "
            "The labels are present and timed from frame zero of the half."
        )
        return 0
    labels = label_times(label_files[0])
    predicted = predicted_times(soccer[0])
    hits, guesses, truths = match(predicted, labels)
    precision = hits / guesses if guesses else 0
    recall = hits / truths if truths else 0
    print(f"hits={hits} predicted={guesses} labels={truths} precision={precision:.2f} recall={recall:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
