import { useState, memo, type RefObject } from "react";
import { ShadowCanvas } from "./ShadowCanvas";
import { FallbackCanvas } from "./FallbackCanvas";
import { ErrorBoundary } from "./ErrorBoundary";
import { useStableCanvasSize } from "../hooks/useStableCanvasSize";
import { getGraphicsProfile } from "../lib/graphicsProfile";

export const SafeShadowCanvas = memo(function SafeShadowCanvas({
  telemetry,
  telemetryRef,
  agentInvokes,
  dreamPreview,
}: {
  telemetry: import("../lib/types").Telemetry | null;
  telemetryRef: RefObject<import("../lib/types").Telemetry | null>;
  agentInvokes?: import("../lib/types").AgentInvoke[];
  dreamPreview?: import("../lib/types").DreamPreview | null;
}) {
  const [mode, setMode] = useState<"webgl" | "fallback">("webgl");
  const { ref: sizeRef, style: sizeStyle } = useStableCanvasSize();
  const tier = getGraphicsProfile().tier;
  const stageClass = `canvas-stage tier-${tier}`;

  const badge = (
    <div
      style={{
        position: "absolute",
        top: 12,
        left: 12,
        zIndex: 2,
        fontSize: "0.6rem",
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        color: mode === "webgl" ? "#6ee7ff" : "#fbbf24",
        background: "rgba(0,0,0,0.45)",
        padding: "4px 8px",
        borderRadius: 4,
        border: `1px solid ${mode === "webgl" ? "rgba(110,231,255,0.3)" : "rgba(251,191,36,0.3)"}`,
      }}
      data-testid="render-mode"
    >
      {mode === "webgl" ? "◉ holographic" : "◎ 2D aperture"}
    </div>
  );

  if (mode === "fallback") {
    return (
      <div ref={sizeRef} className={stageClass} style={sizeStyle}>
        {badge}
        <FallbackCanvas telemetry={telemetry} />
      </div>
    );
  }

  return (
    <div ref={sizeRef} className={stageClass} style={sizeStyle}>
      {badge}
      <ErrorBoundary
        fallback={<FallbackCanvas telemetry={telemetry} />}
      >
        <ShadowCanvas
          telemetryRef={telemetryRef}
          agentInvokes={agentInvokes}
          dreamPreview={dreamPreview}
        />
      </ErrorBoundary>
    </div>
  );
});
