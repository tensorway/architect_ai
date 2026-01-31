import { Plan } from "./types";

function resolveApiUrl(): string {
  if (typeof window === "undefined") return "/architect/generate";

  // Allow manual override for debugging
  const override = (window as any).ARCHITECT_API_URL as string | undefined;
  if (override) return override;

  const host = window.location.hostname || "";
  const isLocal = host === "localhost" || host === "127.0.0.1";
  if (isLocal) return "http://localhost:8000/architect/generate";

  return "/architect/generate";
}

const API_URL = resolveApiUrl();

export async function generatePlanFromText(prompt: string): Promise<Plan> {
  const fallback: Plan = {
    walls: [
      { id: "w1", a: { x: 120, y: 120 }, b: { x: 720, y: 120 } },
      { id: "w2", a: { x: 720, y: 120 }, b: { x: 720, y: 540 } },
      { id: "w3", a: { x: 720, y: 540 }, b: { x: 120, y: 540 } },
      { id: "w4", a: { x: 120, y: 540 }, b: { x: 120, y: 120 } },
      { id: "w5", a: { x: 420, y: 120 }, b: { x: 420, y: 540 } },
    ],
    assets: [],
  };

  try {
    console.debug("[architect] POST", API_URL, { prompt });
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });

    if (!res.ok) throw new Error(`API ${res.status}`);
    const data = await res.json();
    if (!data?.plan?.walls) throw new Error("Malformed API response");
    return data.plan as Plan;
  } catch (err) {
    console.warn("Falling back to local plan; reason:", err);
    return fallback;
  }
}
