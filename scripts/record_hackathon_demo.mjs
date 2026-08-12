/**
 * Boardman hackathon demo recorder (Playwright).
 * Records full spectator + creator flows against production.
 *
 *   node scripts/record_hackathon_demo.mjs
 *   BASE_URL=http://localhost:3456 node scripts/record_hackathon_demo.mjs
 */
import { chromium } from "playwright";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, ".."); // project root
const OUT_DIR = path.join(ROOT, "demos");
const BASE = process.env.BASE_URL || "https://boardman.playingsidequest.fun";

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const videoDir = path.join(OUT_DIR, `record-${stamp}`);
  fs.mkdirSync(videoDir, { recursive: true });

  console.log("Recording Boardman demo →", videoDir);
  console.log("Base:", BASE);

  const browser = await chromium.launch({
    headless: true,
    args: ["--autoplay-policy=no-user-gesture-required"],
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: {
      dir: videoDir,
      size: { width: 1440, height: 900 },
    },
    deviceScaleFactor: 1,
  });

  const page = await context.newPage();

  // —— 1. Product landing ——
  console.log("1) Landing…");
  await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await sleep(2500);

  // —— 2. Game hub ——
  console.log("2) Game hub…");
  await page.goto(`${BASE}/agentic/hub.html`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await sleep(3000);

  // —— 3. Builder docs ——
  console.log("3) Builder docs…");
  await page.goto(`${BASE}/agentic/docs.html`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await sleep(3000);

  // —— 4. Arena spectator flow ——
  console.log("4) Arena spectator…");
  await page.goto(`${BASE}/agentic/arena.html?mode=classic`, {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  await sleep(2000);

  // Ensure spectator view
  const audienceBtn = page.locator("#viewAudience");
  if (await audienceBtn.count()) {
    await audienceBtn.click().catch(() => {});
    await sleep(800);
  }

  // Place a few bets pre-game
  const betA = page.locator("#betA");
  const betB = page.locator("#betB");
  if (await betA.isVisible().catch(() => false)) {
    await betA.click();
    await sleep(600);
    await betB.click();
    await sleep(600);
    await betA.click();
    await sleep(800);
  }

  // Start match
  console.log("5) Play match…");
  const play = page.locator("#btnPlay");
  await play.click();
  await sleep(4000);

  // More bets while live
  for (let i = 0; i < 4; i++) {
    if (await betA.isEnabled().catch(() => false)) {
      await betA.click().catch(() => {});
      await sleep(500);
    }
    if (await betB.isEnabled().catch(() => false)) {
      await betB.click().catch(() => {});
      await sleep(500);
    }
    await sleep(2500);
  }

  // Watch board for a stretch
  console.log("6) Watching game…");
  await sleep(45000);

  // Arena Live mode
  console.log("7) Arena Live view…");
  const arenaMode = page.locator("#modeArena");
  if (await arenaMode.count()) {
    await arenaMode.click().catch(() => {});
    await sleep(8000);
  }
  const classicMode = page.locator("#modeClassic");
  if (await classicMode.count()) {
    await classicMode.click().catch(() => {});
    await sleep(3000);
  }

  // Wait longer for settlement if still playing
  console.log("8) Wait for settle or continue…");
  for (let i = 0; i < 24; i++) {
    const status = await page.locator("#status").textContent().catch(() => "");
    if (/wins|Draw|settled|checkmate|resignation|adjudication/i.test(status || "")) {
      console.log("   status:", status);
      break;
    }
    // if play re-enabled, game ended
    const disabled = await play.isDisabled().catch(() => false);
    if (!disabled && i > 4) {
      console.log("   play re-enabled — match finished");
      break;
    }
    await sleep(5000);
  }
  await sleep(4000);

  // —— Creator desk ——
  console.log("9) Creator desk…");
  const creatorBtn = page.locator("#viewCreator");
  if (await creatorBtn.count()) {
    await creatorBtn.click();
    await sleep(2500);
    // scroll sidebar a bit
    await page.mouse.wheel(0, 400);
    await sleep(1500);
    await page.mouse.wheel(0, 400);
    await sleep(1500);

    // LP top-ups (if not playing)
    const lpNero = page.locator("#btnLpNero");
    if (await lpNero.isEnabled().catch(() => false)) {
      await lpNero.click().catch(() => {});
      await sleep(1000);
      await lpNero.click().catch(() => {});
      await sleep(1000);
    }
    const lpRaja = page.locator("#btnLpRaja");
    if (await lpRaja.isEnabled().catch(() => false)) {
      await lpRaja.click().catch(() => {});
      await sleep(1000);
    }
    await sleep(2000);

    // Reset + short second match to show negotiated stake
    const reset = page.locator("#btnReset");
    if (await reset.isEnabled().catch(() => false)) {
      await reset.click().catch(() => {});
      await sleep(1500);
      await play.click().catch(() => {});
      await sleep(8000);
    }
  }

  // Back to spectator for closing frame
  if (await audienceBtn.count()) {
    await audienceBtn.click().catch(() => {});
    await sleep(2500);
  }

  console.log("10) Hub close…");
  await page.goto(`${BASE}/agentic/hub.html`, { waitUntil: "domcontentloaded" });
  await sleep(2500);

  await context.close();
  await browser.close();

  // Find video file playwright wrote
  const files = fs.readdirSync(videoDir).filter((f) => f.endsWith(".webm"));
  if (!files.length) {
    console.error("No video file produced in", videoDir);
    process.exit(1);
  }
  const src = path.join(videoDir, files[0]);
  const dest = path.join(OUT_DIR, `boardman-hackathon-demo-${stamp}.webm`);
  fs.copyFileSync(src, dest);
  console.log("\n✓ Demo video ready:");
  console.log(" ", dest);
  console.log("Size MB:", (fs.statSync(dest).size / 1024 / 1024).toFixed(2));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
