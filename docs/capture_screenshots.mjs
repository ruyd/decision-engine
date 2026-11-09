// High-DPI (2x) screenshots of the web app for the README. Needs the api + web servers running with demo data.
//   npm i --no-save puppeteer-core && node docs/capture_screenshots.mjs
//   (set WEB_URL=http://localhost:5174 if Vite picked another port; uses the installed Google Chrome;
//    decision 472 is an injected upcoding claim in the demo data - change it to one in yours)
import puppeteer from "puppeteer-core";
import fs from "node:fs";

const BASE = process.env.WEB_URL ?? "http://localhost:5173";
const API = "http://localhost:8000/api";
const OUT = new URL("./screenshots", import.meta.url).pathname;
fs.mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
  args: ["--hide-scrollbars", "--font-render-hinting=none"],
});
const page = await browser.newPage();
const W = 1680;
await page.setViewport({ width: W, height: 900, deviceScaleFactor: 2 });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function shot(name, { maxH = 2200, minH = 900 } = {}) {
  // content scrolls inside <main>; grow the viewport so the whole page is visible
  const h = await page.evaluate(() => document.querySelector("main")?.scrollHeight ?? 900);
  await page.setViewport({ width: W, height: Math.max(minH, Math.min(h, maxH)), deviceScaleFactor: 2 });
  await sleep(1800); // let recharts animations finish after resize
  await page.screenshot({ path: `${OUT}/${name}.png` });
  console.log("saved", name, Math.min(h, maxH));
  await page.setViewport({ width: W, height: 900, deviceScaleFactor: 2 });
}

async function go(path) {
  await page.goto(BASE + path, { waitUntil: "networkidle0" });
  await sleep(1500);
}

const j = (p) => fetch(API + p).then((r) => r.json());

// 1. Overview
await go("/");
await shot("01-overview", { maxH: 1800 });

// 2. Claim decision (injected upcoding, pended by the provider-history rule)
await go("/decisions/472");
await shot("02-claim-decision", { maxH: 1250 });

// 3. Prior auth: submit a request for a very-high-risk member
const vh = (await j("/members?tier=Very%20high&limit=50")).items[7].member_id;
await go("/prior-auth");
await page.type('input[placeholder^="e.g."]', vh);
await page.locator("button ::-p-text(Submit request)").click();
await page.waitForFunction(() => document.body.innerText.includes("Full audit trail"), { timeout: 20000 });
await sleep(800);
await shot("03-prior-auth", { maxH: 1250 });

// 4. Rules: loosen price_outlier to 6x and backtest (draft only, not published)
await go("/rules");
const ta = await page.$$eval("textarea", (els) => els.findIndex((e) => e.value.includes("max_price_ratio >= 10")));
const areas = await page.$$("textarea");
await areas[ta].click({ count: 3 });
await page.keyboard.down("Meta"); await page.keyboard.press("a"); await page.keyboard.up("Meta");
await page.keyboard.type("claim.n_lines_above_p95 >= 2 or claim.max_price_ratio >= 6");
await page.locator("button ::-p-text(Backtest)").click();
await page.waitForFunction(() => document.body.innerText.includes("Backtest on the last"), { timeout: 20000 });
await sleep(500);
await shot("04-rules-backtest", { maxH: 2300 });

// 5. Member risk with dollar SHAP
await go(`/members/${vh}`);
await shot("05-member", { maxH: 1100 });

// 6. Models
await go("/models");
await shot("06-models", { maxH: 900 });

// 7. Review queues
await go("/queues");
await shot("07-queues", { maxH: 900 });

await browser.close();
