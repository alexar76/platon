// Capture sidebar panel crops (steering + witnesses) in English.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";

const UI =
  process.env.PLATON_UI_URL ||
  (process.env.PLATON_CAPTURE_PROD === "1"
    ? "https://oracles.modelmarket.dev/platon/umbral"
    : "http://127.0.0.1:5174");
const SHOTS = join(resolve(process.cwd(), ".."), "docs", "screenshots");
mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  args: ["--use-gl=angle", "--use-angle=swiftshader"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: "en-US" });
await page.goto(UI, { waitUntil: "domcontentloaded" });
const en = page.getByTestId("lang-switch").getByRole("button", { name: "EN" });
if (await en.count()) await en.click();
await page.getByTestId("metric-kappa").waitFor({ state: "visible", timeout: 20000 }).catch(() => {});
await page.waitForTimeout(5000);

async function panelShot(heading, file) {
  const panel = page.locator(".panel").filter({ has: page.getByRole("heading", { name: heading }) });
  const el = panel.first();
  await el.scrollIntoViewIfNeeded();
  const box = await el.boundingBox();
  if (!box) throw new Error(`no bbox for ${heading}`);
  const client = await page.context().newCDPSession(page);
  const { data } = await client.send("Page.captureScreenshot", {
    format: "png",
    clip: { x: box.x, y: box.y, width: box.width, height: box.height, scale: 1 },
  });
  const fs = await import("node:fs");
  fs.writeFileSync(join(SHOTS, file), Buffer.from(data, "base64"));
}

await panelShot("Incarnation · semantic steering", "03-steering.png");
const witness = page.locator("[data-testid=witness-feed]");
await witness.scrollIntoViewIfNeeded();
const wbox = await witness.boundingBox();
if (wbox) {
  const client = await page.context().newCDPSession(page);
  const { data } = await client.send("Page.captureScreenshot", {
    format: "png",
    clip: { x: wbox.x, y: wbox.y, width: wbox.width, height: Math.min(wbox.height, 220), scale: 1 },
  });
  const fs = await import("node:fs");
  fs.writeFileSync(join(SHOTS, "04-witnesses.png"), Buffer.from(data, "base64"));
}

await browser.close();
console.log("panel screenshots ->", SHOTS);
