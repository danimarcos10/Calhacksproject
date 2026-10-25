export type Fit = {
  scale: number;
  offsetX: number;
  offsetY: number;
};

export type Point = { x: number; y: number };

export type Box = { x: number; y: number; w: number; h: number };

/** Contain-fit. Mouse input is in CSS pixels, not device pixels. */
export function containFit(imageWidth: number, imageHeight: number, canvasCssWidth: number, canvasCssHeight: number): Fit {
  const scale = Math.min(canvasCssWidth / imageWidth, canvasCssHeight / imageHeight);
  return {
    scale,
    offsetX: (canvasCssWidth - scale * imageWidth) / 2,
    offsetY: (canvasCssHeight - scale * imageHeight) / 2,
  };
}

export function deviceSize(cssWidth: number, cssHeight: number, devicePixelRatio: number) {
  const ratio = devicePixelRatio || 1;
  return { width: cssWidth * ratio, height: cssHeight * ratio, ratio };
}

/** Returns null when the point is in the letterbox, outside the image. */
export function cssToNormalized(
  cssX: number,
  cssY: number,
  imageWidth: number,
  imageHeight: number,
  canvasCssWidth: number,
  canvasCssHeight: number,
): Point | null {
  const { scale, offsetX, offsetY } = containFit(imageWidth, imageHeight, canvasCssWidth, canvasCssHeight);
  const x = (cssX - offsetX) / (scale * imageWidth);
  const y = (cssY - offsetY) / (scale * imageHeight);
  if (x < 0 || y < 0 || x > 1 || y > 1) return null;
  return { x, y };
}

export function normalizedToCss(
  x: number,
  y: number,
  imageWidth: number,
  imageHeight: number,
  canvasCssWidth: number,
  canvasCssHeight: number,
): Point {
  const { scale, offsetX, offsetY } = containFit(imageWidth, imageHeight, canvasCssWidth, canvasCssHeight);
  return { x: offsetX + x * scale * imageWidth, y: offsetY + y * scale * imageHeight };
}

export function boxFromPoints(start: Point, end: Point): Box | null {
  const x = Math.min(start.x, end.x);
  const y = Math.min(start.y, end.y);
  const w = Math.abs(end.x - start.x);
  const h = Math.abs(end.y - start.y);
  if (w < 0.02 || h < 0.02) return null;
  return { x: round4(x), y: round4(y), w: round4(w), h: round4(h) };
}

export function clampToImage(cssX: number, cssY: number, imageWidth: number, imageHeight: number, canvasCssWidth: number, canvasCssHeight: number): Point {
  const inside = cssToNormalized(cssX, cssY, imageWidth, imageHeight, canvasCssWidth, canvasCssHeight);
  if (inside) return inside;
  const { scale, offsetX, offsetY } = containFit(imageWidth, imageHeight, canvasCssWidth, canvasCssHeight);
  return {
    x: clamp01((cssX - offsetX) / (scale * imageWidth)),
    y: clamp01((cssY - offsetY) / (scale * imageHeight)),
  };
}

function clamp01(value: number) {
  return Math.min(1, Math.max(0, value));
}

function round4(value: number) {
  return Math.round(value * 10000) / 10000;
}
