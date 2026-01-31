import { dist, mid, snapToGrid, setLengthFromA } from "./geometry";
import { parseSvgText } from "./svgParser";
import { flashButton } from "./flashButton";

export function runTests() {
  console.assert(Math.abs(dist({ x: 0, y: 0 }, { x: 3, y: 4 }) - 5) < 1e-9, "dist 3-4-5");
  const m = mid({ x: 0, y: 0 }, { x: 10, y: 6 });
  console.assert(m.x === 5 && m.y === 3, "midpoint");
  const s = snapToGrid({ x: 11, y: 29 }, 10);
  console.assert(s.x === 10 && s.y === 30, "snapToGrid");
  const b2 = setLengthFromA({ x: 0, y: 0 }, { x: 10, y: 0 }, 25);
  console.assert(Math.abs(b2.x - 25) < 1e-9 && Math.abs(b2.y) < 1e-9, "setLengthFromA");

  const example = `<?xml version="1.0" encoding="UTF-8" standalone="no"?>
  <svg viewBox="0 0 10 5" xmlns="http://www.w3.org/2000/svg"><rect x="0" y="0" width="10" height="5"/></svg>`;
  const p = parseSvgText(example);
  console.assert(p.vbW === 10 && p.vbH === 5, "parseSvgText viewBox");
  console.assert(p.inner.includes("rect"), "parseSvgText inner");

  try {
    flashButton("__missing__");
    console.assert(true, "flashButton no-throw");
  } catch {
    console.assert(false, "flashButton should not throw");
  }
}
