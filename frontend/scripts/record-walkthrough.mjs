/**
 * Record the cantina demo walkthrough as a video.
 *
 * Drives the demo container (deploy/demo/) with a real browser and captures a
 * ~60s tour: sign in → the dashboard (catalog, meals, "what you can make right
 * now") → the Spending page and its weeks-of-history chart (the differentiator
 * for a tracker) → the grocery list → inventory.
 *
 * This is a recording, not a test — it lives outside any test dir so CI never
 * runs it. It expects the fabricated demo data, so point it at a demo container,
 * never a real instance:
 *
 *   docker build -f deploy/demo/Dockerfile -t cantina-demo .
 *   docker run -d --name cantina-demo-rec -p 3200:8000 cantina-demo
 *   cd frontend && node scripts/record-walkthrough.mjs
 *
 * Output: docs/video/walkthrough.webm. Pacing is deliberate — the pauses are
 * what make it watchable, so the wall-clock runtime IS the video length.
 */
import { chromium } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.resolve(__dirname, "../../docs/video");

const BASE = process.env.DEMO_URL || "http://localhost:3200";
const SIZE = { width: 1280, height: 800 };

// Named beats so the pacing is tunable in one place.
const BEAT = { tick: 700, read: 1600, settle: 2400 };
const pause = (page, ms) => page.waitForTimeout(ms);

// cantina is a hash-routed SPA: nav links flip which <main> is visible rather
// than changing the path, so we click the nav and wait on the view, not the URL.
async function goto(page, route, viewId) {
  await page.locator(`nav.topnav a[data-route="${route}"]`).click();
  await page.locator(`#${viewId}`).waitFor({ state: "visible" });
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: SIZE,
    recordVideo: { dir: OUT_DIR, size: SIZE },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();

  // --- 1. Sign in ------------------------------------------------------------
  await page.goto(BASE);
  await page.locator("#login-form").waitFor();
  await pause(page, BEAT.read);
  // Type it out — a filled-in form appearing instantly reads as a page reload.
  await page.locator('#login-form input[name="email"]').type("demo@cantina.local", { delay: 70 });
  await page.locator('#login-form input[name="password"]').type("demopass123", { delay: 70 });
  await pause(page, BEAT.tick);
  await page.getByRole("button", { name: "Sign in" }).click();

  // --- 2. The dashboard: a stocked household ---------------------------------
  await page.locator("#view-dashboard").waitFor({ state: "visible" });
  await page.getByRole("heading", { name: "Foods", exact: true }).waitFor();
  await pause(page, BEAT.settle);
  // Scroll down to the menu — "what you can make right now" from what's on hand.
  await page.getByRole("heading", { name: "Menu", exact: true }).scrollIntoViewIfNeeded();
  await pause(page, BEAT.settle);

  // --- 3. The hero: the Spending page + its history chart --------------------
  await goto(page, "/spending", "view-spending");
  await pause(page, BEAT.read);
  // Let the chart sit — the weeks of spending history are the differentiator.
  await pause(page, BEAT.settle * 2);

  // --- 4. The grocery list ---------------------------------------------------
  await goto(page, "/list", "view-list");
  await pause(page, BEAT.settle);

  // --- 5. Inventory: what's on hand ------------------------------------------
  await goto(page, "/inventory", "view-inventory");
  await pause(page, BEAT.settle);

  // --- 6. Land back on the dashboard -----------------------------------------
  await goto(page, "/", "view-dashboard");
  await pause(page, BEAT.settle);

  // Video is only flushed to disk on context.close().
  const video = page.video();
  await context.close();
  await browser.close();

  const dest = path.join(OUT_DIR, "walkthrough.webm");
  fs.renameSync(await video.path(), dest);
  const mb = (fs.statSync(dest).size / 1e6).toFixed(1);
  console.log(`Wrote ${dest} (${mb} MB)`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
