import { describe, expect, it } from "vitest";
import { boxFromPoints, containFit, cssToNormalized, deviceSize, normalizedToCss } from "./geometry";

describe("contain-fit boxes", () => {
  it("round-trips a point on a landscape frame", () => {
    const point = cssToNormalized(320, 180, 1920, 1080, 640, 360);
    expect(point).toEqual({ x: 0.5, y: 0.5 });
    const back = normalizedToCss(0.5, 0.5, 1920, 1080, 640, 360);
    expect(back.x).toBeCloseTo(320);
    expect(back.y).toBeCloseTo(180);
  });

  it("rejects the letterbox around a portrait frame", () => {
    const fit = containFit(180, 320, 640, 360);
    expect(fit.offsetX).toBeGreaterThan(0);
    expect(fit.offsetY).toBeCloseTo(0);
    expect(cssToNormalized(4, 40, 180, 320, 640, 360)).toBeNull();
    const inside = cssToNormalized(fit.offsetX + 20, 40, 180, 320, 640, 360);
    expect(inside).not.toBeNull();
    const restored = normalizedToCss(inside!.x, inside!.y, 180, 320, 640, 360);
    expect(restored.x).toBeCloseTo(fit.offsetX + 20);
    expect(restored.y).toBeCloseTo(40);
  });

  it("keeps the same normalized box after the canvas is resized", () => {
    const wide = cssToNormalized(100, 50, 320, 180, 400, 200);
    const narrowCanvas = { w: 200, h: 120 };
    const again = normalizedToCss(wide!.x, wide!.y, 320, 180, narrowCanvas.w, narrowCanvas.h);
    const back = cssToNormalized(again.x, again.y, 320, 180, narrowCanvas.w, narrowCanvas.h);
    expect(back!.x).toBeCloseTo(wide!.x);
    expect(back!.y).toBeCloseTo(wide!.y);
  });

  it("keeps CSS coordinates independent of the device pixel ratio", () => {
    const stored = cssToNormalized(30, 40, 100, 50, 200, 100);
    const low = deviceSize(200, 100, 1);
    const high = deviceSize(200, 100, 2);
    expect(high.width).toBe(low.width * 2);
    expect(stored).toEqual(cssToNormalized(30, 40, 100, 50, low.width / 1, low.height / 1));
  });

  it("builds a box from the drag corners", () => {
    expect(boxFromPoints({ x: 0.2, y: 0.1 }, { x: 0.5, y: 0.4 })).toEqual({ x: 0.2, y: 0.1, w: 0.3, h: 0.3 });
    expect(boxFromPoints({ x: 0.2, y: 0.2 }, { x: 0.21, y: 0.21 })).toBeNull();
  });
});
