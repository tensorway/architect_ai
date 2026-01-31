import type React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { clamp, dist, mid, metersToPx, pxToMeters, setLengthFromA, snapToGrid } from "./geometry";
import { parseSvgText } from "./svgParser";
import { flashButton } from "./flashButton";
import { generatePlanFromText } from "./planGenerator";
import { runTests } from "./tests";
import { Plan, Pt, Selection, SvgAsset, ViewState, Wall } from "./types";

const VIEWBOX = { width: 1200, height: 800 };
const GRID = 20;
const SCALE_PX_PER_M = 100;
const DEFAULT_PROMPT =
  "Design a 1-bed flat ~45m² with living+kitchen, bathroom, and a bedroom.";

const SYMBOLS = {
  TV: {
    name: "TV",
    svg: `<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg width="68.529091mm" height="6.6113729mm" viewBox="0 0 68.529092 6.6113729" xmlns="http://www.w3.org/2000/svg">
  <g transform="translate(-16.044039,-83.803322)">
    <g>
      <rect style="fill:none;stroke:#000000;stroke-width:0.75" width="61.756626" height="3.2600846" x="19.430269" y="84.178322" />
      <rect style="fill:none;stroke:#000000;stroke-width:0.75" width="67.779091" height="2.6012869" x="16.419039" y="87.438408" />
    </g>
  </g>
</svg>`,
    defaultWidthM: 1.2,
  },
} as const;

type SymbolKey = keyof typeof SYMBOLS;
type DragState =
  | null
  | { mode: "pan"; startClient: Pt; startView: ViewState }
  | { mode: "handle"; wallId: string; which: "a" | "b" }
  | { mode: "asset"; assetId: string; startWorld: Pt; startPos: Pt };

function uid(prefix = "id") {
  return `${prefix}_${Math.random().toString(36).slice(2, 9)}`;
}

export default function App() {
  useEffect(() => {
    runTests();
  }, []);

  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [plan, setPlan] = useState<Plan>(() => ({
    walls: [
      { id: "w1", a: { x: 100, y: 100 }, b: { x: 700, y: 100 } },
      { id: "w2", a: { x: 700, y: 100 }, b: { x: 700, y: 500 } },
      { id: "w3", a: { x: 700, y: 500 }, b: { x: 100, y: 500 } },
      { id: "w4", a: { x: 100, y: 500 }, b: { x: 100, y: 100 } },
      { id: "w5", a: { x: 400, y: 100 }, b: { x: 400, y: 500 } }
    ],
    assets: [],
  }));
  const [selection, setSelection] = useState<Selection>({ type: "wall", id: "w1" });
  const [view, setView] = useState<ViewState>({ x: 0, y: 0, scale: 1 });
  const [isGenerating, setIsGenerating] = useState(false);
  const [ioJson, setIoJson] = useState("");
  const [showExport, setShowExport] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState<SymbolKey>("TV");
  const [newWallLengthM, setNewWallLengthM] = useState(3);
  const [newWallOrientation, setNewWallOrientation] = useState<"horizontal" | "vertical">("horizontal");

  const dragRef = useRef<DragState>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const selectedWall = useMemo(() => {
    if (selection?.type !== "wall") return null;
    return plan.walls.find((w) => w.id === selection.id) ?? null;
  }, [plan.walls, selection]);

  const selectedAsset = useMemo(() => {
    if (selection?.type !== "asset") return null;
    return plan.assets.find((a) => a.id === selection.id) ?? null;
  }, [plan.assets, selection]);

  const gridLines = useMemo(() => {
    const lines: { x1: number; y1: number; x2: number; y2: number }[] = [];
    for (let x = 0; x <= VIEWBOX.width; x += GRID) lines.push({ x1: x, y1: 0, x2: x, y2: VIEWBOX.height });
    for (let y = 0; y <= VIEWBOX.height; y += GRID) lines.push({ x1: 0, y1: y, x2: VIEWBOX.width, y2: y });
    return lines;
  }, []);

  function updateWallEndpoint(id: string, which: "a" | "b", next: Pt) {
    setPlan((p) => ({
      ...p,
      walls: p.walls.map((w) => (w.id === id ? { ...w, [which]: next } : w)),
    }));
  }

  function updateWall(id: string, patch: Partial<Wall>) {
    setPlan((p) => ({
      ...p,
      walls: p.walls.map((w) => (w.id === id ? { ...w, ...patch } : w)),
    }));
  }

  function updateAsset(id: string, patch: Partial<SvgAsset>) {
    setPlan((p) => ({
      ...p,
      assets: p.assets.map((a) => (a.id === id ? { ...a, ...patch } : a)),
    }));
  }

  async function handleGenerate() {
    setIsGenerating(true);
    flashButton("generate-btn");
    try {
      const next = await generatePlanFromText(prompt);
      setPlan(next);
      const firstWall = next.walls?.[0];
      setSelection(firstWall ? { type: "wall", id: firstWall.id } : null);
    } catch (err) {
      console.error("[architect] generate failed", err);
    } finally {
      setIsGenerating(false);
    }
  }

  function onSave() {
    const payload = { plan, view, prompt };
    const json = JSON.stringify(payload, null, 2);
    setIoJson(json);

    const isSandbox = typeof location !== "undefined" && location.host.includes("web-sandbox.oaiusercontent.com");
    if (!isSandbox) {
      try {
        const blob = new Blob([json], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "floorplan.json";
        a.rel = "noopener";
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 250);
        flashButton("save-btn");
        return;
      } catch {
        /* noop */
      }
    }

    setShowExport(true);
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(json).catch(() => {});
    }
    flashButton("save-btn");
  }

  async function onLoadFile(file: File) {
    const text = await file.text();
    const parsed = JSON.parse(text);
    if (!parsed?.plan) throw new Error("Invalid file");
    setPlan(parsed.plan);
    setView(parsed.view ?? { x: 0, y: 0, scale: 1 });
    setPrompt(parsed.prompt ?? "");
    setSelection(parsed.plan.walls?.[0]?.id ? { type: "wall", id: parsed.plan.walls[0].id } : null);
    flashButton("load-btn");
  }

  function onPickLoad() {
    fileInputRef.current?.click();
  }

  function setSelectedWallLengthMeters(m: number) {
    if (!selectedWall) return;
    const newLenPx = metersToPx(m, SCALE_PX_PER_M);
    const newB = setLengthFromA(selectedWall.a, selectedWall.b, newLenPx);
    updateWall(selectedWall.id, { b: snapToGrid(newB, GRID) });
  }

  function addSymbol() {
    try {
      const symbol = SYMBOLS[selectedSymbol];
      const parsed = parseSvgText(symbol.svg);
      const desiredWidthPx = metersToPx(symbol.defaultWidthM, SCALE_PX_PER_M);
      const scale = desiredWidthPx / parsed.vbW;
      const pos = snapToGrid({ x: 140, y: 140 }, GRID);

      const asset: SvgAsset = {
        id: uid("asset"),
        name: symbol.name,
        inner: parsed.inner,
        vbW: parsed.vbW,
        vbH: parsed.vbH,
        x: pos.x,
        y: pos.y,
        scale,
        rotationDeg: 0,
      };

      setPlan((p) => ({ ...p, assets: [...p.assets, asset] }));
      setSelection({ type: "asset", id: asset.id });
      setView((v) => ({ ...v, x: 600 - asset.x * v.scale, y: 400 - asset.y * v.scale }));
      flashButton("add-symbol-btn");
    } catch {
      /* noop for hard-coded symbols */
    }
  }

  function addWall() {
    const lenPx = metersToPx(Math.max(0, newWallLengthM || 0), SCALE_PX_PER_M);
    const centerWorld = snapToGrid(
      {
        x: (600 - view.x) / view.scale,
        y: (400 - view.y) / view.scale,
      },
      GRID
    );

    const snappedLenPx = Math.round(lenPx / GRID) * GRID;
    const b: Pt =
      newWallOrientation === "horizontal"
        ? { x: centerWorld.x + snappedLenPx, y: centerWorld.y }
        : { x: centerWorld.x, y: centerWorld.y + snappedLenPx };

    const id = uid("w");
    const wall: Wall = { id, a: centerWorld, b };
    setPlan((p) => ({ ...p, walls: [...p.walls, wall] }));
    setSelection({ type: "wall", id });
    flashButton("add-wall-btn");
  }

  function clientToWorld(client: Pt): Pt {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const rect = svg.getBoundingClientRect();
    const sx = client.x - rect.left;
    const sy = client.y - rect.top;
    return {
      x: (sx - view.x) / view.scale,
      y: (sy - view.y) / view.scale,
    };
  }

  function onWheel(e: React.WheelEvent) {
    e.preventDefault();
    const svg = svgRef.current;
    if (!svg) return;

    const rect = svg.getBoundingClientRect();
    const pointer = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    const scaleBy = 1.08;
    const direction = e.deltaY > 0 ? -1 : 1;
    const newScale = clamp(view.scale * (direction > 0 ? scaleBy : 1 / scaleBy), 0.2, 6);
    const mousePointTo = {
      x: (pointer.x - view.x) / view.scale,
      y: (pointer.y - view.y) / view.scale,
    };
    const newPos = {
      x: pointer.x - mousePointTo.x * newScale,
      y: pointer.y - mousePointTo.y * newScale,
    };

    setView({ x: newPos.x, y: newPos.y, scale: newScale });
  }

  function onPointerDownBackground(e: React.PointerEvent) {
    const target = e.target as HTMLElement;
    if (target?.dataset?.role && target.dataset.role !== "background") return;

    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    dragRef.current = {
      mode: "pan",
      startClient: { x: e.clientX, y: e.clientY },
      startView: { ...view },
    };
  }

  function onPointerMove(e: React.PointerEvent) {
    const st = dragRef.current;
    if (!st) return;

    if (st.mode === "pan") {
      const dx = e.clientX - st.startClient.x;
      const dy = e.clientY - st.startClient.y;
      setView({ x: st.startView.x + dx, y: st.startView.y + dy, scale: st.startView.scale });
      return;
    }

    if (st.mode === "handle") {
      const world = clientToWorld({ x: e.clientX, y: e.clientY });
      const snapped = snapToGrid(world, GRID);
      updateWallEndpoint(st.wallId, st.which, snapped);
      return;
    }

    if (st.mode === "asset") {
      const world = clientToWorld({ x: e.clientX, y: e.clientY });
      const dx = world.x - st.startWorld.x;
      const dy = world.y - st.startWorld.y;
      const next = snapToGrid({ x: st.startPos.x + dx, y: st.startPos.y + dy }, GRID);
      updateAsset(st.assetId, { x: next.x, y: next.y });
    }
  }

  function onPointerUp(e: React.PointerEvent) {
    dragRef.current = null;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  }

  const selectedLenPx = selectedWall ? dist(selectedWall.a, selectedWall.b) : 0;
  const selectedLenM = selectedWall ? pxToMeters(selectedLenPx, SCALE_PX_PER_M) : 0;

  return (
    <div className="app-root">
      <style>{`
        .app-root {
          display: grid;
          grid-template-columns: 360px 1fr;
          grid-template-areas: "sidebar canvas";
          height: 100dvh;
          min-height: 0;
        }
        .canvas { min-width: 0; min-height: 0; }
        .canvas svg { width: 100%; height: 100%; display: block; }
        @media (max-width: 768px) {
          .app-root {
            grid-template-columns: 1fr;
            grid-template-rows: 58dvh auto;
            grid-template-areas: "canvas" "sidebar";
          }
          .sidebar { border-right: none !important; border-top: 1px solid #eee; }
        }
        .btn {
          width: 100%;
          padding: 8px 12px;
          border-radius: 6px;
          border: 1px solid #ccc;
          background: #fff;
          color: #111;
          font-weight: 500;
          cursor: pointer;
          transition: background 0.15s ease, box-shadow 0.15s ease, transform 0.05s ease;
        }
        .btn:hover { background: #f5f5f5; box-shadow: 0 1px 2px rgba(0,0,0,0.08); }
        .btn:active { transform: translateY(1px); box-shadow: 0 0 0 rgba(0,0,0,0); }
        .btn-primary { background: #111; color: #fff; border-color: #111; }
        .btn-primary:hover { background: #000; }
        .btn-flash { animation: flash 0.6s ease; }
        @keyframes flash {
          0% { box-shadow: 0 0 0 0 rgba(0,0,0,0.4); }
          50% { box-shadow: 0 0 0 4px rgba(0,0,0,0.15); }
          100% { box-shadow: 0 0 0 0 rgba(0,0,0,0); }
        }
        .sidebar {
          background: #fff;
        }
        .sidebar hr {
          border: 0;
          border-top: 1px solid #eee;
          margin: 14px 0;
        }
        .sidebar input,
        .sidebar select,
        .sidebar textarea {
          width: 100%;
          box-sizing: border-box;
          padding: 10px 10px;
          border: 1px solid #e1e1e1;
          border-radius: 8px;
          background: #fff;
          outline: none;
          font-size: 14px;
        }
        .sidebar textarea {
          resize: vertical;
          min-height: 90px;
          line-height: 1.35;
        }
        .sidebar input:focus,
        .sidebar select:focus,
        .sidebar textarea:focus {
          border-color: #bdbdbd;
          box-shadow: 0 0 0 3px rgba(0,0,0,0.06);
        }
        .sidebar input[type=number] { -moz-appearance: textfield; appearance: textfield; }
        .sidebar input[type=number]::-webkit-outer-spin-button,
        .sidebar input[type=number]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
      `}</style>

      <div
        className="sidebar"
        style={{ gridArea: "sidebar", padding: 16, borderRight: "1px solid #eee", fontFamily: "system-ui" }}
      >
        <div style={{ fontSize: 12, marginBottom: 6 }}>Prompt</div>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={5} />
        <button
          id="generate-btn"
          onClick={handleGenerate}
          className="btn btn-primary"
          disabled={isGenerating}
          style={isGenerating ? { opacity: 0.55, cursor: "not-allowed" } : undefined}
        >
          {isGenerating ? "Generating…" : "Generate"}
        </button>

        <hr style={{ margin: "14px 0" }} />

        <div style={{ fontWeight: 600, marginBottom: 4 }}>Edit</div>
        <div style={{ fontSize: 12, color: "#555", marginBottom: 8 }}>Click / select an element on the canvas to edit it</div>

        <div style={{ fontSize: 12, marginBottom: 6 }}>Selection</div>
        <select
          value={selection ? `${selection.type}:${selection.id}` : ""}
          onChange={(e) => {
            const [type, id] = e.target.value.split(":");
            if (type === "wall") setSelection({ type: "wall", id });
            else if (type === "asset") setSelection({ type: "asset", id });
            else setSelection(null);
          }}
        >
          {plan.walls.map((w) => (
            <option key={`wall:${w.id}`} value={`wall:${w.id}`}>
              Wall {w.id}
            </option>
          ))}
          {plan.assets.map((a) => (
            <option key={`asset:${a.id}`} value={`asset:${a.id}`}>
              Asset {a.name}
            </option>
          ))}
        </select>

        {selection?.type === "wall" && selectedWall && (
          <>
            <div style={{ marginTop: 10, fontSize: 12 }}>Length (meters)</div>
            <input
              type="text"
              inputMode="decimal"
              value={String(selectedLenM.toFixed(2))}
              onChange={(e) => {
                const v = e.target.value.replace(/[^0-9.]/g, "");
                setSelectedWallLengthMeters(parseFloat(v || "0"));
              }}
              style={{
                width: "100%",
                padding: "6px 8px",
                border: "1px solid #ccc",
                borderRadius: 6,
                fontVariantNumeric: "tabular-nums",
              }}
            />
          </>
        )}

        {selection?.type === "asset" && selectedAsset && (
          <>
            <div style={{ marginTop: 10, fontSize: 12 }}>Selected</div>
            <div style={{ fontSize: 12, color: "#555" }}>{selectedAsset.name}</div>
          </>
        )}

        <div style={{ marginTop: 10, fontSize: 12, color: "#555" }}>
          Drag endpoints to edit walls. Drag background to pan. Mouse wheel to zoom.
        </div>

        <hr style={{ margin: "14px 0" }} />

        <div style={{ fontWeight: 600, marginBottom: 8 }}>
          Add windows, doors or furnature
        </div>
        <div style={{ fontSize: 12, marginBottom: 6 }}>Symbol</div>
        <select value={selectedSymbol} onChange={(e) => setSelectedSymbol(e.target.value as SymbolKey)}>
          {Object.keys(SYMBOLS).map((k) => (
            <option key={k} value={k}>
              {SYMBOLS[k as SymbolKey].name}
            </option>
          ))}
        </select>
        <button id="add-symbol-btn" onClick={addSymbol} className="btn">
          Add
        </button>

        <hr style={{ margin: "14px 0" }} />

        <div style={{ fontWeight: 600, marginBottom: 8 }}>Add wall</div>
        <div style={{ fontSize: 12, marginBottom: 6 }}>Orientation</div>
        <select value={newWallOrientation} onChange={(e) => setNewWallOrientation(e.target.value as any)}>
          <option value="horizontal">Horizontal</option>
          <option value="vertical">Vertical</option>
        </select>

        <div style={{ marginTop: 8, fontSize: 12, marginBottom: 6 }}>Length (meters)</div>
        <input
          type="text"
          inputMode="decimal"
          value={String(newWallLengthM.toFixed(2))}
          onChange={(e) => {
            const v = e.target.value.replace(/[^0-9.]/g, "");
            setNewWallLengthM(parseFloat(v || "0"));
          }}
          style={{
            width: "100%",
            padding: "6px 8px",
            border: "1px solid #ccc",
            borderRadius: 6,
            fontVariantNumeric: "tabular-nums",
          }}
        />

        <button id="add-wall-btn" onClick={addWall} className="btn">
          Add
        </button>

        <div style={{ marginTop: 10, fontSize: 12, color: "#555" }}>
          New wall appears at the current view center. Drag endpoints to reshape.
        </div>

        <hr style={{ margin: "14px 0" }} />

        <div style={{ fontWeight: 600, marginBottom: 8 }}>Save / Load</div>
        <button id="save-btn" onClick={onSave} className="btn">
          Save
        </button>
        <button id="load-btn" onClick={onPickLoad} className="btn">
          Load
        </button>

        {showExport ? (
          <div style={{ marginTop: 10 }}>
            <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
              <button
                className="btn"
                id="copy-btn"
                onClick={() => {
                  if (navigator.clipboard?.writeText) {
                    navigator.clipboard.writeText(ioJson).catch(() => {});
                  }
                  flashButton("copy-btn");
                }}
              >
                Copy JSON
              </button>
              <button className="btn" onClick={() => setShowExport(false)}>
                Hide
              </button>
            </div>
            <textarea
              readOnly
              value={ioJson}
              rows={8}
              style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" }}
            />
            <div style={{ marginTop: 6, fontSize: 12, color: "#555" }}>
              If you need a file: paste this JSON into a file named <b>floorplan.json</b>.
            </div>
          </div>
        ) : null}

        <input
          ref={fileInputRef}
          type="file"
          accept="application/json"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            onLoadFile(f).catch((err) => alert(err.message));
            e.currentTarget.value = "";
          }}
        />
      </div>

      <div className="canvas" style={{ gridArea: "canvas", background: "#fafafa" }}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${VIEWBOX.width} ${VIEWBOX.height}`}
          preserveAspectRatio="xMidYMid meet"
          style={{ touchAction: "none", display: "block" }}
          onWheel={onWheel}
          onPointerDown={onPointerDownBackground}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        >
          <rect data-role="background" x={0} y={0} width={VIEWBOX.width} height={VIEWBOX.height} fill="#fafafa" />

          <g transform={`translate(${view.x} ${view.y}) scale(${view.scale})`}>
            <g>
              {gridLines.map((l, i) => (
                <line
                  key={i}
                  x1={l.x1}
                  y1={l.y1}
                  x2={l.x2}
                  y2={l.y2}
                  stroke="rgba(0,0,0,0.06)"
                  strokeWidth={1}
                />
              ))}
            </g>

            <g>
              {plan.assets.map((a) => {
                const isSel = selection?.type === "asset" && selection.id === a.id;
                const t = `translate(${a.x} ${a.y}) rotate(${a.rotationDeg}) scale(${a.scale})`;
                return (
                  <g
                    key={a.id}
                    data-role="asset"
                    transform={t}
                    onPointerDown={(e) => {
                      e.stopPropagation();
                      setSelection({ type: "asset", id: a.id });
                      (e.currentTarget as SVGGElement).setPointerCapture(e.pointerId);
                      const startWorld = clientToWorld({ x: e.clientX, y: e.clientY });
                      dragRef.current = {
                        mode: "asset",
                        assetId: a.id,
                        startWorld,
                        startPos: { x: a.x, y: a.y },
                      };
                    }}
                    style={{ cursor: "grab" }}
                  >
                    <g
                      style={{ stroke: "#111", fill: "none", strokeWidth: 1.5, opacity: 0.95 }}
                      dangerouslySetInnerHTML={{ __html: a.inner }}
                    />
                    <rect x={0} y={0} width={a.vbW} height={a.vbH} fill="transparent" />
                  </g>
                );
              })}
            </g>

            <g>
              {plan.walls.map((w) => {
                const isSel = selection?.type === "wall" && selection.id === w.id;
                const mpt = mid(w.a, w.b);
                const dx = w.b.x - w.a.x;
                const dy = w.b.y - w.a.y;
                const len = Math.hypot(dx, dy) || 1;
                const nx = -dy / len;
                const ny = dx / len;
                const labelOffset = 14;
                const labelPos = { x: mpt.x + nx * labelOffset, y: mpt.y + ny * labelOffset };
                const lenM = pxToMeters(dist(w.a, w.b), SCALE_PX_PER_M);
                return (
                  <g key={w.id}>
                    <line
                      x1={w.a.x}
                      y1={w.a.y}
                      x2={w.b.x}
                      y2={w.b.y}
                      stroke={isSel ? "#000" : "#333"}
                      strokeWidth={4}
                      strokeLinecap="square"
                      onPointerDown={(e) => {
                        e.stopPropagation();
                        setSelection({ type: "wall", id: w.id });
                      }}
                      style={{ cursor: "pointer" }}
                    />

                    <text x={labelPos.x} y={labelPos.y} fontSize={14} fill="#111" style={{ userSelect: "none" }}>
                      {lenM.toFixed(2)}m
                    </text>

                    {([
                      { which: "a" as const, p: w.a },
                      { which: "b" as const, p: w.b },
                    ] as const).map(({ which, p }) => (
                      <circle
                        key={which}
                        cx={p.x}
                        cy={p.y}
                        r={8}
                        fill={isSel ? "#000" : "#fff"}
                        stroke="#000"
                        strokeWidth={2}
                        onPointerDown={(e) => {
                          e.stopPropagation();
                          setSelection({ type: "wall", id: w.id });
                          (e.currentTarget as SVGCircleElement).setPointerCapture(e.pointerId);
                          dragRef.current = { mode: "handle", wallId: w.id, which };
                        }}
                        style={{ cursor: "grab" }}
                      />
                    ))}
                  </g>
                );
              })}
            </g>
          </g>
        </svg>
      </div>
    </div>
  );
}
