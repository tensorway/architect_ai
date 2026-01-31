import { Plan } from "./types";

export function generatePlanFromText(_prompt: string): Plan {
  return {
    walls: [
      { id: "w1", a: { x: 100, y: 100 }, b: { x: 700, y: 100 } },
      { id: "w2", a: { x: 700, y: 100 }, b: { x: 700, y: 500 } },
      { id: "w3", a: { x: 700, y: 500 }, b: { x: 100, y: 500 } },
      { id: "w4", a: { x: 100, y: 500 }, b: { x: 100, y: 100 } },
      { id: "w5", a: { x: 400, y: 100 }, b: { x: 400, y: 500 } }
    ],
    assets: [],
  };
}
