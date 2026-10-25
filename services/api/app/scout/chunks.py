"""Chunk bounds and overlap stitching. Detection stays per chunk; time stays monotonic."""

from __future__ import annotations

from app.scout.identity import Point


def chunk_ranges(start_ms: int, end_ms: int, chunk_ms: int = 15_000, overlap_ms: int = 1_000) -> list[tuple[int, int]]:
    if end_ms <= start_ms:
        return []
    ranges: list[tuple[int, int]] = []
    cursor = start_ms
    while cursor < end_ms:
        stop = min(end_ms, cursor + chunk_ms)
        ranges.append((cursor, stop))
        if stop == end_ms:
            break
        nxt = stop - overlap_ms
        if nxt <= cursor:
            break
        cursor = nxt
    return ranges


def stitch(chunks: list[list[Point]]) -> list[Point]:
    """Keep the earlier chunk's point where chunks overlap, in source-time order."""
    merged: list[Point] = []
    seen: set[int] = set()
    for chunk in chunks:
        for point in chunk:
            if point.t_ms in seen:
                continue
            seen.add(point.t_ms)
            merged.append(point)
    merged.sort(key=lambda point: point.t_ms)
    return merged


def parse_showinfo_pts(line: str) -> int | None:
    """Milliseconds from an ffmpeg showinfo line. Returns None when the line has no pts."""
    marker = "pts_time:"
    start = line.find(marker)
    if start < 0:
        return None
    raw = line[start + len(marker) :].split(" ", 1)[0].split("\t", 1)[0]
    try:
        return int(round(float(raw) * 1000))
    except ValueError:
        return None
