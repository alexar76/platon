export type GraphicsTier = "full" | "mobile" | "android";

export type GraphicsProfile = {
  tier: GraphicsTier;
  dpr: number | [number, number];
  starsFar: number;
  starsNear: number;
  sparkles: [number, number, number];
  bloom: number;
  chromatic: boolean;
  antialias: boolean;
  powerPreference: WebGLPowerPreference;
  preserveDrawingBuffer: boolean;
  resizeDebounceMs: number;
  adaptiveDpr: boolean;
  /** GPU postprocessing (Bloom) — ping-pong buffers flicker on Android Chrome. */
  postprocess: boolean;
};

const FULL: GraphicsProfile = {
  tier: "full",
  dpr: [1, 2],
  starsFar: 6000,
  starsNear: 2600,
  sparkles: [200, 140, 90],
  bloom: 1.35,
  chromatic: true,
  antialias: true,
  powerPreference: "high-performance",
  preserveDrawingBuffer: false,
  resizeDebounceMs: 250,
  adaptiveDpr: true,
  postprocess: true,
};

const MOBILE: GraphicsProfile = {
  tier: "mobile",
  dpr: 1.25,
  starsFar: 2400,
  starsNear: 1000,
  sparkles: [130, 90, 55],
  bloom: 1.28,
  chromatic: true,
  antialias: false,
  powerPreference: "default",
  preserveDrawingBuffer: true,
  resizeDebounceMs: 600,
  adaptiveDpr: false,
  postprocess: true,
};

/** Android Chrome + Mali/Adreno: skip EffectComposer, compensate with CSS glow. */
const ANDROID: GraphicsProfile = {
  tier: "android",
  dpr: 1,
  starsFar: 2000,
  starsNear: 800,
  sparkles: [100, 70, 45],
  bloom: 0,
  chromatic: false,
  antialias: false,
  powerPreference: "default",
  preserveDrawingBuffer: false,
  resizeDebounceMs: 800,
  adaptiveDpr: false,
  postprocess: false,
};

function isAndroid(): boolean {
  return /Android/i.test(navigator.userAgent);
}

export function getGraphicsProfile(): GraphicsProfile {
  if (typeof window === "undefined") return FULL;
  const coarse = window.matchMedia("(pointer: coarse)").matches;
  const narrow = window.matchMedia("(max-width: 900px)").matches;
  const mem = (navigator as Navigator & { deviceMemory?: number }).deviceMemory;
  const touch = coarse || narrow;

  if (isAndroid() && touch) return ANDROID;
  if (touch || (mem !== undefined && mem < 4)) return MOBILE;
  return FULL;
}
