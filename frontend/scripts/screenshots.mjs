/**
 * Capture the README screenshots from the demo container (docs/img/).
 *
 * Same idea as record-walkthrough.mjs: drive the seeded demo with a real browser
 * so the screenshots are the real UI, not mockups. Point it at a demo container:
 *
 *   docker run -d --name cantina-demo-shots -p 3200:8000 cantina-demo
 *   cd frontend && node scripts/screenshots.mjs
 *
 * Output: docs/img/dashboard.png, docs/img/spending.png
 */
import { chromium } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.resolve(__dirname, "../../docs/img");
const BASE = process.env.DEMO_URL || "http://localhost:3200";
const SIZE = { width: 1280, height: 800 };

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: SIZE, deviceScaleFactor: 2 });
  const page = await context.newPage();

  // Sign in.
  await page.goto(BASE);
  await page.locator("#login-form").waitFor();
  await page.locator('#login-form input[name="email"]').fill("demo@cantina.local");
  await page.locator('#login-form input[name="password"]').fill("demopass123");
  await page.getByRole("button", { name: "Sign in" }).click();

  // Dashboard.
  await page.locator("#view-dashboard").waitFor({ state: "visible" });
  await page.getByRole("heading", { name: "Foods", exact: true }).waitFor();
  await page.waitForTimeout(600); // let cards/menu settle
  await page.screenshot({ path: path.join(OUT_DIR, "dashboard.png"), fullPage: true });

  // Spending.
  await page.locator('nav.topnav a[data-route="/spending"]').click();
  await page.locator("#view-spending").waitFor({ state: "visible" });
  await page.waitForTimeout(800); // let the chart render
  await page.screenshot({ path: path.join(OUT_DIR, "spending.png"), fullPage: true });

  await context.close();
  await browser.close();
  for (const f of ["dashboard.png", "spending.png"]) {
    const p = path.join(OUT_DIR, f);
    console.log(`Wrote ${p} (${(fs.statSync(p).size / 1e3).toFixed(0)} KB)`);
  }
}

main().catch((err) => { console.error(err); process.exit(1); });
