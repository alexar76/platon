// Capture the gallery screenshots + a video of the 32D structure.
// Usage: node scripts/gallery.mjs  (backend on :9200, vite on :5174 must be up)
import { chromium } from "@playwright/test";
import { existsSync, mkdirSync, readdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const UI =
  process.env.PLATON_UI_URL ||
  (process.env.PLATON_CAPTURE_PROD === "1"
    ? "https://oracles.modelmarket.dev/platon/umbral"
    : "http://127.0.0.1:5174");
const ROOT = resolve(process.cwd(), "..");
const SHOTS = join(ROOT, "docs", "screenshots");
const RECS = join(ROOT, "docs", "recordings");
mkdirSync(SHOTS, { recursive: true });
mkdirSync(RECS, { recursive: true });

// Headed + GPU on macOS is most reliable; Linux CI uses headless + SwiftShader.
const headless = process.env.PLATON_CAPTURE_HEADED !== "1";
const browser = await chromium.launch({
  headless,
  args: headless ? ["--use-gl=angle", "--use-angle=swiftshader"] : [],
});

async function ensureEnglish(page) {
  const en = page.getByTestId("lang-switch").getByRole("button", { name: "EN" });
  if (await en.count()) await en.click();
}

async function cdpClipShot(page, locator, outPath, maxHeight) {
  await locator.scrollIntoViewIfNeeded().catch(() => {});
  const box = await locator.boundingBox();
  if (!box) return;
  const client = await page.context().newCDPSession(page);
  const height = maxHeight ? Math.min(box.height, maxHeight) : box.height;
  const { data } = await client.send("Page.captureScreenshot", {
    format: "png",
    clip: { x: box.x, y: box.y, width: box.width, height, scale: 1 },
  });
  writeFileSync(outPath, Buffer.from(data, "base64"));
}

async function panelShot(page, heading, outPath) {
  const panel = page.locator(".panel").filter({ has: page.getByRole("heading", { name: heading }) });
  await cdpClipShot(page, panel.first(), outPath);
}

// --- screenshots ---
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  locale: "en-US",
});
await page.goto(UI, { waitUntil: "networkidle" });
await ensureEnglish(page);
await page.getByTestId("metric-kappa").waitFor({ state: "visible", timeout: 20000 }).catch(() => {});
await page.waitForTimeout(6000); // let the cosmos animate & oscillators populate

await page.screenshot({ path: join(SHOTS, "01-main-view.png") });
await page.screenshot({ path: join(SHOTS, "05-cosmos.png") });

const shot = async (testidOrSel, file) => {
  const loc = testidOrSel.startsWith(".")
    ? page.locator(testidOrSel)
    : page.getByTestId(testidOrSel);
  if (!(await loc.count())) return;
  const target = loc.first();
  await target.scrollIntoViewIfNeeded().catch(() => {});
  await page.waitForTimeout(400);
  try {
    await target.screenshot({ path: join(SHOTS, file), timeout: 10000 });
  } catch {
    // Sidebar panels can be unstable while telemetry animates — clip from full page.
    const box = await target.boundingBox();
    if (box) {
      await page.screenshot({
        path: join(SHOTS, file),
        clip: {
          x: Math.max(0, box.x),
          y: Math.max(0, box.y),
          width: Math.min(box.width, 1440 - box.x),
          height: Math.min(box.height, 900 - box.y),
        },
      });
    }
  }
};
await shot("metrics-panel", "02-telemetry.png");
await panelShot(page, "Incarnation · semantic steering", join(SHOTS, "03-steering.png"));
await cdpClipShot(page, page.locator("[data-testid=witness-feed]"), join(SHOTS, "04-witnesses.png"), 220);
await page.close();

// --- video of the 32D structure ---
const tmp = join(RECS, "_tmp");
if (existsSync(tmp)) rmSync(tmp, { recursive: true, force: true });
mkdirSync(tmp, { recursive: true });
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  locale: "en-US",
  recordVideo: { dir: tmp, size: { width: 1280, height: 720 } },
});
const vp = await ctx.newPage();
await vp.goto(UI, { waitUntil: "networkidle" });
await ensureEnglish(vp);
await vp.getByTestId("metric-kappa").waitFor({ state: "visible", timeout: 20000 }).catch(() => {});
await vp.waitForTimeout(4000);
// rotate Stiefel projection so the wireframe icosahedron orbits visibly
if (await vp.getByRole("button", { name: "θ₁=0.3" }).count()) {
  await vp.getByRole("button", { name: "θ₁=0.3" }).click();
  await vp.waitForTimeout(1500);
  await vp.getByRole("button", { name: "θ₂=2.0" }).click();
  await vp.waitForTimeout(1500);
}
if (await vp.getByTestId("steer-input").count()) {
  await vp.getByTestId("steer-input").fill("entropy cathedral at criticality");
  await vp.getByTestId("steer-btn").click();
}
await vp.waitForTimeout(3000);
if (await vp.getByTestId("dream-btn").count()) await vp.getByTestId("dream-btn").click();
await vp.waitForTimeout(3500);
await vp.close();
await ctx.close();

const vids = readdirSync(tmp).filter((f) => f.endsWith(".webm"));
if (vids.length) {
  renameSync(join(tmp, vids[0]), join(RECS, "platon-cosmos.webm"));
  rmSync(tmp, { recursive: true, force: true });
  console.log("video -> docs/recordings/platon-cosmos.webm");
}
await browser.close();
console.log("screenshots ->", SHOTS);
