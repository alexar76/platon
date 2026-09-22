import { useEffect, useRef, useState } from "react";
import { getGraphicsProfile } from "../lib/graphicsProfile";

/**
 * Freeze canvas container height on mobile after first layout.
 * Safari URL-bar show/hide changes dvh and retriggers WebGL resize → flicker.
 */
export function useStableCanvasSize() {
  const ref = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number | undefined>();
  const mobile = getGraphicsProfile().tier !== "full";

  useEffect(() => {
    if (!mobile) return;
    const el = ref.current;
    if (!el) return;

    const lock = () => {
      const h = el.getBoundingClientRect().height;
      if (h > 100) setHeight((prev) => prev ?? Math.round(h));
    };

    lock();
    const t = window.setTimeout(lock, 120);
    return () => window.clearTimeout(t);
  }, [mobile]);

  const style =
    mobile && height
      ? { height, minHeight: height, maxHeight: height, flexShrink: 0 as const }
      : undefined;

  return { ref, style, mobile };
}
