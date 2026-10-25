import { describe, expect, it } from "vitest";
import { buildPlaylist, playlistCount, playlistMs, type PlayableMoment } from "./moments";

const clip = { vid_a: 20_000 };

function moment(id: string, startMs: number, endMs: number, status: PlayableMoment["status"], videoKey = "vid_a"): PlayableMoment {
  return { id, videoKey, startMs, endMs, status };
}

describe("buildPlaylist", () => {
  it("pads for playback and keeps the exact evidence times", () => {
    const [segment] = buildPlaylist([moment("m1", 3_000, 4_000, "suggestion")], "current", clip, 1_500);
    expect(segment).toMatchObject({ startMs: 1_500, endMs: 5_500 });
    expect(segment.moments).toEqual([{ id: "m1", startMs: 3_000, endMs: 4_000 }]);
  });

  it("clamps padding to the start and end of the clip", () => {
    const segments = buildPlaylist(
      [moment("start", 0, 1_084, "accepted"), moment("end", 19_500, 20_000, "accepted")],
      "accepted",
      clip,
      1_500,
    );
    expect(segments.map((s) => [s.startMs, s.endMs])).toEqual([
      [0, 2_584],
      [18_000, 20_000],
    ]);
  });

  it("merges intervals whose padded playback overlaps", () => {
    const segments = buildPlaylist(
      [moment("b", 5_000, 6_000, "suggestion"), moment("a", 2_000, 3_000, "accepted")],
      "current",
      clip,
      1_500,
    );
    expect(segments).toHaveLength(1);
    expect(segments[0]).toMatchObject({ startMs: 500, endMs: 7_500 });
    expect(segments[0].moments.map((m) => m.id)).toEqual(["a", "b"]);
    expect(playlistCount(segments)).toBe("2 in 1 segment");
  });

  it("keeps moments far apart as separate segments", () => {
    const segments = buildPlaylist(
      [moment("a", 3_000, 4_000, "suggestion"), moment("b", 10_000, 11_000, "suggestion")],
      "current",
      clip,
      1_500,
    );
    expect(segments).toHaveLength(2);
    expect(playlistMs(segments)).toBe(4_000 + 4_000);
    expect(playlistCount(segments)).toBe("2");
  });

  it("leaves rejected and stale moments out of every playlist", () => {
    const moments = [
      moment("s", 1_000, 2_000, "suggestion"),
      moment("h", 4_000, 5_000, "held"),
      moment("a", 8_000, 9_000, "accepted"),
      moment("r", 12_000, 13_000, "rejected"),
      moment("x", 16_000, 17_000, "stale"),
    ];
    const current = buildPlaylist(moments, "current", clip, 0).flatMap((s) => s.moments.map((m) => m.id));
    const accepted = buildPlaylist(moments, "accepted", clip, 0).flatMap((s) => s.moments.map((m) => m.id));
    expect(current).toEqual(["s", "h", "a"]);
    expect(accepted).toEqual(["a"]);
  });

  it("never merges intervals from different clips", () => {
    const segments = buildPlaylist(
      [moment("a", 1_000, 2_000, "accepted", "vid_a"), moment("b", 1_000, 2_000, "accepted", "vid_b")],
      "accepted",
      { vid_a: 20_000, vid_b: 20_000 },
      1_500,
    );
    expect(segments.map((s) => s.videoKey)).toEqual(["vid_a", "vid_b"]);
  });
});
