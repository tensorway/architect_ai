export type Pt = { x: number; y: number };

export type Wall = {
  id: string;
  a: Pt;
  b: Pt;
};

export type SvgAsset = {
  id: string;
  name: string;
  inner: string;
  vbW: number;
  vbH: number;
  x: number;
  y: number;
  scale: number;
  rotationDeg: number;
};

export type Plan = {
  walls: Wall[];
  assets: SvgAsset[];
};

export type Selection =
  | { type: "wall"; id: string }
  | { type: "asset"; id: string }
  | null;

export type ViewState = { x: number; y: number; scale: number };
