import { Pt } from "./types";

export function dist(a: Pt, b: Pt) {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.hypot(dx, dy);
}

export function mid(a: Pt, b: Pt): Pt {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

export function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

export function snapToGrid(p: Pt, grid: number): Pt {
  return { x: Math.round(p.x / grid) * grid, y: Math.round(p.y / grid) * grid };
}

export function setLengthFromA(a: Pt, b: Pt, newLen: number): Pt {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const s = newLen / len;
  return { x: a.x + dx * s, y: a.y + dy * s };
}

export function pxToMeters(px: number, scalePxPerM: number) {
  return px / scalePxPerM;
}

export function metersToPx(m: number, scalePxPerM: number) {
  return m * scalePxPerM;
}
