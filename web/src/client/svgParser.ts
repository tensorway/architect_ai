export function parseSvgText(svgText: string): { inner: string; vbW: number; vbH: number } {
  const trimmed = svgText.trim();
  const parser = new DOMParser();
  const doc = parser.parseFromString(trimmed, "image/svg+xml");

  const parseErr = doc.querySelector("parsererror");
  if (parseErr) throw new Error("Invalid SVG (parsererror)");

  const svgEl = doc.querySelector("svg");
  if (!svgEl) throw new Error("Invalid SVG: missing <svg>");

  const vb = svgEl.getAttribute("viewBox");
  let vbW = 0;
  let vbH = 0;

  if (vb) {
    const parts = vb
      .split(/[ ,]+/)
      .map((s) => s.trim())
      .filter(Boolean)
      .map((s) => Number(s));
    if (parts.length === 4 && parts.every((n) => Number.isFinite(n))) {
      vbW = parts[2];
      vbH = parts[3];
    }
  }

  if (!(vbW > 0 && vbH > 0)) {
    const wAttr = svgEl.getAttribute("width") ?? "";
    const hAttr = svgEl.getAttribute("height") ?? "";
    const w = Number.parseFloat(wAttr);
    const h = Number.parseFloat(hAttr);
    if (Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0) {
      vbW = w;
      vbH = h;
    } else {
      vbW = 100;
      vbH = 100;
    }
  }

  svgEl.querySelectorAll("script").forEach((n) => n.remove());
  const inner = svgEl.innerHTML;
  if (!inner.trim()) throw new Error("SVG has no drawable content");

  return { inner, vbW, vbH };
}
