/** Resolve paths under the Vite base (production: `/platon/`). */
export function platonUrl(path: string): string {
  const base = import.meta.env.BASE_URL || "/";
  const root = base.endsWith("/") ? base : `${base}/`;
  return `${root}${path.replace(/^\//, "")}`;
}

export function platonWsUrl(): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const base = (import.meta.env.BASE_URL || "/").replace(/\/$/, "");
  const path = `${base}/ws`.replace(/\/{2,}/g, "/");
  return `${proto}//${location.host}${path.startsWith("/") ? path : `/${path}`}`;
}
