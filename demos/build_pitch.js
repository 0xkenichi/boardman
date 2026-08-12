/**
 * Boardman — Professional pitch deck (Encode Arc Programmable Money)
 * Standard startup narrative — not a feature dump or demo recap.
 */
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const pres = new pptxgen();
pres.defineLayout({ name: "WIDE", width: 13.333, height: 7.5 });
pres.layout = "WIDE";
pres.author = "sideQuest";
pres.title = "Boardman — Pitch Deck";
pres.subject = "Arc Programmable Money Hackathon";

// ── Design system (institutional fintech) ──────────────────────────
const C = {
  bg: "0B1220",
  bgAlt: "111827",
  card: "151C2C",
  line: "1F2937",
  text: "F8FAFC",
  muted: "94A3B8",
  dim: "64748B",
  accent: "7C3AED",
  accentSoft: "A78BFA",
  green: "10B981",
  cyan: "22D3EE",
  white: "FFFFFF",
};

const FONT = { h: "Calibri", b: "Calibri" };

function sh() {
  return { type: "outer", color: "000000", blur: 18, offset: 4, angle: 135, opacity: 0.35 };
}

function slide() {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  return s;
}

function footer(s, page, total = 12) {
  s.addText("BOARDMAN", {
    x: 0.6, y: 7.1, w: 3, h: 0.25,
    fontSize: 10, fontFace: FONT.b, color: C.dim, margin: 0, bold: true, charSpacing: 1.5,
  });
  s.addText("CONFIDENTIAL", {
    x: 5.2, y: 7.1, w: 3, h: 0.25,
    fontSize: 10, fontFace: FONT.b, color: C.dim, margin: 0, align: "center",
  });
  s.addText(String(page) + " / " + String(total), {
    x: 11.0, y: 7.1, w: 1.7, h: 0.25,
    fontSize: 10, fontFace: FONT.b, color: C.dim, margin: 0, align: "right",
  });
}

function sectionLabel(s, text) {
  s.addText(text.toUpperCase(), {
    x: 0.7, y: 0.35, w: 12, h: 0.28,
    fontSize: 11, fontFace: FONT.b, color: C.accentSoft, bold: true, margin: 0, charSpacing: 2,
  });
}

function title(s, text, y = 0.65) {
  s.addText(text, {
    x: 0.7, y, w: 12, h: 0.7,
    fontSize: 32, fontFace: FONT.h, color: C.text, bold: true, margin: 0,
  });
}

// ═══════════════════════════════════════════════════════════════════
// 1. TITLE
// ═══════════════════════════════════════════════════════════════════
{
  const s = slide();
  // left accent panel
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.18, h: 7.5, fill: { color: C.accent },
  });
  s.addText("ARC  ·  PROGRAMMABLE MONEY  ·  2026", {
    x: 0.9, y: 1.55, w: 11, h: 0.3,
    fontSize: 12, fontFace: FONT.b, color: C.accentSoft, bold: true, margin: 0, charSpacing: 2.5,
  });
  s.addText("Boardman", {
    x: 0.9, y: 2.1, w: 11, h: 0.9,
    fontSize: 54, fontFace: FONT.h, color: C.white, bold: true, margin: 0,
  });
  s.addText("The settlement layer for skill contests—\nhuman and autonomous—denominated in USDC.", {
    x: 0.9, y: 3.15, w: 10.5, h: 1.0,
    fontSize: 20, fontFace: FONT.b, color: C.muted, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.9, y: 4.5, w: 2.2, h: 0.06, fill: { color: C.accent },
  });
  s.addText("sideQuest  ·  DeFi Track & Agentic Economy Track", {
    x: 0.9, y: 4.85, w: 10, h: 0.35,
    fontSize: 14, fontFace: FONT.b, color: C.dim, margin: 0,
  });
  s.addText("boardman.playingsidequest.fun", {
    x: 0.9, y: 6.35, w: 10, h: 0.3,
    fontSize: 13, fontFace: FONT.b, color: C.dim, margin: 0,
  });
}

// ═══════════════════════════════════════════════════════════════════
// 2. PROBLEM
// ═══════════════════════════════════════════════════════════════════
{
  const s = slide();
  sectionLabel(s, "The problem");
  title(s, "Skill has a market. Settlement does not.");
  s.addText("Billions of informal wagers already happen around games of skill—console 1v1s, local tournaments, online ladders. Almost none settle as programmable money.", {
    x: 0.7, y: 1.45, w: 12, h: 0.7,
    fontSize: 15, fontFace: FONT.b, color: C.muted, margin: 0,
  });

  const problems = [
    { n: "01", t: "Trust-based settlement", d: "Cash, chat apps, and IOUs. Disputes are social, not contractual. Capital cannot scale." },
    { n: "02", t: "Crypto UX fails the user", d: "Seed phrases, gas tokens, and multi-step bridges kill conversion for mainstream players." },
    { n: "03", t: "Agents are not economic actors", d: "AI can play—but without wallets, policy, fees, and markets, agents cannot participate in an economy." },
  ];
  problems.forEach((p, i) => {
    const x = 0.7 + i * 4.15;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.45, w: 3.95, h: 3.7, fill: { color: C.card }, shadow: sh(),
    });
    s.addText(p.n, {
      x: x + 0.3, y: 2.75, w: 3.3, h: 0.45,
      fontSize: 22, fontFace: FONT.h, color: C.accent, bold: true, margin: 0,
    });
    s.addText(p.t, {
      x: x + 0.3, y: 3.4, w: 3.3, h: 0.7,
      fontSize: 18, fontFace: FONT.h, color: C.text, bold: true, margin: 0,
    });
    s.addText(p.d, {
      x: x + 0.3, y: 4.25, w: 3.3, h: 1.5,
      fontSize: 14, fontFace: FONT.b, color: C.muted, margin: 0,
    });
  });
  footer(s, 2);
}

// ═══════════════════════════════════════════════════════════════════
// 3. SOLUTION
// ═══════════════════════════════════════════════════════════════════
{
  const s = slide();
  sectionLabel(s, "The solution");
  title(s, "One rail. Two participants. Same money.");
  s.addText("Boardman is programmable settlement infrastructure for finite-outcome skill contests—starting on Arc with USDC.", {
    x: 0.7, y: 1.4, w: 12, h: 0.55,
    fontSize: 15, fontFace: FONT.b, color: C.muted, margin: 0,
  });

  // Two columns
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 2.2, w: 5.85, h: 4.2, fill: { color: C.card }, shadow: sh(),
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 2.2, w: 0.12, h: 4.2, fill: { color: C.cyan },
  });
  s.addText("HUMANS", {
    x: 1.15, y: 2.5, w: 5, h: 0.35,
    fontSize: 12, fontFace: FONT.b, color: C.cyan, bold: true, margin: 0, charSpacing: 1.5,
  });
  s.addText("Skill matches that settle", {
    x: 1.15, y: 2.95, w: 5, h: 0.45,
    fontSize: 20, fontFace: FONT.h, color: C.text, bold: true, margin: 0,
  });
  s.addText([
    { text: "Challenge a peer, dual-lock USDC", options: { bullet: true, breakLine: true } },
    { text: "Play offline or online (console first)", options: { bullet: true, breakLine: true } },
    { text: "Proof via AI vision on result media", options: { bullet: true, breakLine: true } },
    { text: "Winner paid automatically from escrow", options: { bullet: true } },
  ], {
    x: 1.15, y: 3.6, w: 5, h: 2.4,
    fontSize: 14, fontFace: FONT.b, color: C.muted, paraSpaceAfter: 10,
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.8, y: 2.2, w: 5.85, h: 4.2, fill: { color: C.card }, shadow: sh(),
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.8, y: 2.2, w: 0.12, h: 4.2, fill: { color: C.accent },
  });
  s.addText("AGENTS", {
    x: 7.25, y: 2.5, w: 5, h: 0.35,
    fontSize: 12, fontFace: FONT.b, color: C.accentSoft, bold: true, margin: 0, charSpacing: 1.5,
  });
  s.addText("An economy for AI players", {
    x: 7.25, y: 2.95, w: 5, h: 0.45,
    fontSize: 20, fontFace: FONT.h, color: C.text, bold: true, margin: 0,
  });
  s.addText([
    { text: "Agents hold bankrolls and policies", options: { bullet: true, breakLine: true } },
    { text: "Negotiate equal stakes from free capital", options: { bullet: true, breakLine: true } },
    { text: "Creators earn fees on wins", options: { bullet: true, breakLine: true } },
    { text: "Spectators and LPs provide side capital", options: { bullet: true } },
  ], {
    x: 7.25, y: 3.6, w: 5, h: 2.4,
    fontSize: 14, fontFace: FONT.b, color: C.muted, paraSpaceAfter: 10,
  });
  footer(s, 3);
}

// ═══════════════════════════════════════════════════════════════════
// 4. PRODUCT
// ═══════════════════════════════════════════════════════════════════
{
  const s = slide();
  sectionLabel(s, "Product");
  title(s, "Three products. One settlement stack.");

  const products = [
    { k: "01", t: "Boardman App", s: "Consumer", d: "Telegram-native skill 1v1s with dual-lock escrow, wallets, and proof-based settle." },
    { k: "02", t: "Agent Arena", s: "Market", d: "Autonomous matches with live odds, capped spectator pots, and creator economics." },
    { k: "03", t: "Boardman Stack", s: "Platform", d: "Builder APIs: register agents, plug games, open books, settle skill + spectator rails." },
  ];
  products.forEach((p, i) => {
    const y = 1.55 + i * 1.6;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.7, y, w: 12, h: 1.4, fill: { color: C.card }, shadow: sh(),
    });
    s.addText(p.k, {
      x: 1.0, y: y + 0.4, w: 1.0, h: 0.55,
      fontSize: 22, fontFace: FONT.h, color: C.accent, bold: true, margin: 0,
    });
    s.addText(p.t, {
      x: 2.2, y: y + 0.25, w: 6, h: 0.4,
      fontSize: 20, fontFace: FONT.h, color: C.text, bold: true, margin: 0,
    });
    s.addText(p.s.toUpperCase(), {
      x: 9.5, y: y + 0.3, w: 2.8, h: 0.35,
      fontSize: 11, fontFace: FONT.b, color: C.accentSoft, bold: true, margin: 0, align: "right", charSpacing: 1,
    });
    s.addText(p.d, {
      x: 2.2, y: y + 0.75, w: 10, h: 0.45,
      fontSize: 14, fontFace: FONT.b, color: C.muted, margin: 0,
    });
  });
  footer(s, 4);
}

// ═══════════════════════════════════════════════════════════════════
// 5. HOW IT WORKS
// ═══════════════════════════════════════════════════════════════════
{
  const s = slide();
  sectionLabel(s, "Architecture");
  title(s, "Two money rails. Never mixed.");
  s.addText("Every match has a canonical skill outcome. Spectator markets are a side book keyed to the same match—not a second conflicting pot.", {
    x: 0.7, y: 1.4, w: 12, h: 0.55,
    fontSize: 14, fontFace: FONT.b, color: C.muted, margin: 0,
  });

  // Flow boxes
  const steps = [
    { t: "Fund", d: "Owner or LP\ncapitalizes\nagent bankroll" },
    { t: "Negotiate", d: "Equal stake\nfrom free capital\n& policy caps" },
    { t: "Lock", d: "Dual-lock skill\nescrow + seed\nspectator pot" },
    { t: "Play", d: "Finite outcome\ncontest (chess\nfirst)" },
    { t: "Settle", d: "Platform fee\ncreator fee\nbankroll / bets" },
  ];
  steps.forEach((st, i) => {
    const x = 0.55 + i * 2.55;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.25, w: 2.35, h: 2.9, fill: { color: C.card }, shadow: sh(),
    });
    s.addShape(pres.shapes.OVAL, {
      x: x + 0.85, y: 2.5, w: 0.55, h: 0.55, fill: { color: C.accent },
    });
    s.addText(String(i + 1), {
      x: x + 0.85, y: 2.58, w: 0.55, h: 0.45,
      fontSize: 16, fontFace: FONT.h, color: C.white, bold: true, align: "center", margin: 0,
    });
    s.addText(st.t, {
      x: x + 0.15, y: 3.25, w: 2.05, h: 0.4,
      fontSize: 16, fontFace: FONT.h, color: C.text, bold: true, align: "center", margin: 0,
    });
    s.addText(st.d, {
      x: x + 0.15, y: 3.75, w: 2.05, h: 1.15,
      fontSize: 12, fontFace: FONT.b, color: C.muted, align: "center", margin: 0,
    });
    if (i < steps.length - 1) {
      s.addShape(pres.shapes.RIGHT_ARROW, {
        x: x + 2.2, y: 3.45, w: 0.28, h: 0.22, fill: { color: C.dim },
      });
    }
  });
  s.addText("Hard rule: skill escrow ≠ spectator pot. Same match_id. Separate ledgers. One outcome.", {
    x: 0.7, y: 5.5, w: 12, h: 0.4,
    fontSize: 13, fontFace: FONT.b, color: C.accentSoft, italic: true, margin: 0,
  });
  footer(s, 5);
}

// ═══════════════════════════════════════════════════════════════════
// 6. ECONOMIC DESIGN
// ═══════════════════════════════════════════════════════════════════
{
  const s = slide();
  sectionLabel(s, "Economic design");
  title(s, "Aligned incentives across four roles.");

  const roles = [
    { t: "Players / Agents", d: "Risk bankroll on skill. Wins compound free capital; losses require top-up." },
    { t: "Creators", d: "Deploy minds and policy. Earn a configurable cut of skill wins (capped)." },
    { t: "Spectators", d: "Stake any amount up to pot room. Pari-mutuel odds; ~5% total take." },
    { t: "Liquidity providers", d: "Back an agent’s bankroll for a share of net skill profit—not fixed yield." },
  ];
  roles.forEach((r, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.7 + col * 6.25;
    const y = 1.55 + row * 2.35;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 6.0, h: 2.15, fill: { color: C.card }, shadow: sh(),
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.1, h: 2.15, fill: { color: i % 2 === 0 ? C.accent : C.cyan },
    });
    s.addText(r.t, {
      x: x + 0.4, y: y + 0.35, w: 5.3, h: 0.45,
      fontSize: 18, fontFace: FONT.h, color: C.text, bold: true, margin: 0,
    });
    s.addText(r.d, {
      x: x + 0.4, y: y + 0.95, w: 5.3, h: 0.85,
      fontSize: 14, fontFace: FONT.b, color: C.muted, margin: 0,
    });
  });
  footer(s, 6);
}

// ═══════════════════════════════════════════════════════════════════
// 7. BUSINESS MODEL
// ═══════════════════════════════════════════════════════════════════
{
  const s = slide();
  sectionLabel(s, "Business model");
  title(s, "Transparent take. Sustainable at volume.");

  // Fee table visual
  const fees = [
    { rail: "Skill escrow", rate: "3.0%", note: "Platform fee on dual-lock pot (BoardmanEscrow-aligned)" },
    { rail: "Creator skill fee", rate: "3–10%", note: "Of winner gross; set at deploy; hard-capped" },
    { rail: "Spectator pot", rate: "5.0%", note: "3% platform + 2% creator pool on side market" },
    { rail: "LP share", rate: "Policy", note: "Default ~40% of net skill profit to LPs; residual to bankroll" },
  ];
  // header
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 1.55, w: 12, h: 0.55, fill: { color: C.bgAlt },
  });
  s.addText("RAIL", { x: 1.0, y: 1.65, w: 3.2, h: 0.35, fontSize: 11, bold: true, color: C.dim, margin: 0, charSpacing: 1 });
  s.addText("RATE", { x: 4.4, y: 1.65, w: 1.8, h: 0.35, fontSize: 11, bold: true, color: C.dim, margin: 0, charSpacing: 1 });
  s.addText("NOTES", { x: 6.5, y: 1.65, w: 5.8, h: 0.35, fontSize: 11, bold: true, color: C.dim, margin: 0, charSpacing: 1 });

  fees.forEach((f, i) => {
    const y = 2.15 + i * 0.85;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.7, y, w: 12, h: 0.75, fill: { color: i % 2 ? C.card : C.bgAlt },
    });
    s.addText(f.rail, { x: 1.0, y: y + 0.2, w: 3.2, h: 0.4, fontSize: 15, bold: true, color: C.text, margin: 0 });
    s.addText(f.rate, { x: 4.4, y: y + 0.2, w: 1.8, h: 0.4, fontSize: 15, bold: true, color: C.accentSoft, margin: 0 });
    s.addText(f.note, { x: 6.5, y: y + 0.2, w: 5.8, h: 0.4, fontSize: 13, color: C.muted, margin: 0 });
  });
  s.addText("Design intent: thin enough for bettors and agents to return; thick enough to fund infrastructure.", {
    x: 0.7, y: 5.7, w: 12, h: 0.4,
    fontSize: 13, fontFace: FONT.b, color: C.dim, italic: true, margin: 0,
  });
  footer(s, 7);
}

// ═══════════════════════════════════════════════════════════════════
// 8. WHY ARC
// ═══════════════════════════════════════════════════════════════════
{
  const s = slide();
  sectionLabel(s, "Why Arc");
  title(s, "Stablecoin settlement is the product.");

  const why = [
    { t: "USDC as unit of account", d: "Stakes, seeds, fees, and pots are all stable value—matching how skill markets already price risk." },
    { t: "Gas UX for real users", d: "USDC-native settlement narrative removes the “find test ETH first” drop-off that kills consumer crypto." },
    { t: "High-frequency, small ticket", d: "Agent loops and casual 1v1s need cheap, predictable settlement—not casino-scale gas variance." },
    { t: "Programmable policy", d: "Escrow, free capital, seed bps, pot caps, and creator fees are code—not social convention." },
  ];
  why.forEach((w, i) => {
    const y = 1.5 + i * 1.2;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.7, y, w: 12, h: 1.05, fill: { color: C.card }, shadow: sh(),
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.7, y, w: 0.12, h: 1.05, fill: { color: C.accent },
    });
    s.addText(w.t, {
      x: 1.15, y: y + 0.15, w: 11.2, h: 0.35,
      fontSize: 16, fontFace: FONT.h, color: C.text, bold: true, margin: 0,
    });
    s.addText(w.d, {
      x: 1.15, y: y + 0.55, w: 11.2, h: 0.35,
      fontSize: 13, fontFace: FONT.b, color: C.muted, margin: 0,
    });
  });
  footer(s, 8);
}

// ═══════════════════════════════════════════════════════════════════
// 9. MARKET
// ═══════════════════════════════════════════════════════════════════
{
  const s = slide();
  sectionLabel(s, "Market");
  title(s, "Where skill capital already lives.");

  // Three market wedges
  const mk = [
    { t: "Skill gaming", m: "Primary", d: "Console & mobile 1v1s, local tournaments, game centers—especially emerging markets where cash stakes are common but rails are not." },
    { t: "Agent economies", m: "Expansion", d: "Autonomous competitors need wallets, matchmaking, and fee markets. Chess is the reference game; the stack is game-agnostic." },
    { t: "Spectator markets", m: "Overlay", d: "Side liquidity on finite outcomes—prediction without replacing the skill escrow that defines the contest." },
  ];
  mk.forEach((m, i) => {
    const x = 0.7 + i * 4.15;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.55, w: 3.95, h: 4.5, fill: { color: C.card }, shadow: sh(),
    });
    s.addText(m.m.toUpperCase(), {
      x: x + 0.3, y: 1.85, w: 3.35, h: 0.3,
      fontSize: 11, fontFace: FONT.b, color: C.accentSoft, bold: true, margin: 0, charSpacing: 1.5,
    });
    s.addText(m.t, {
      x: x + 0.3, y: 2.35, w: 3.35, h: 0.7,
      fontSize: 22, fontFace: FONT.h, color: C.text, bold: true, margin: 0,
    });
    s.addText(m.d, {
      x: x + 0.3, y: 3.3, w: 3.35, h: 2.3,
      fontSize: 14, fontFace: FONT.b, color: C.muted, margin: 0,
    });
  });
  footer(s, 9);
}

// ═══════════════════════════════════════════════════════════════════
// 10. TRACTION
// ═══════════════════════════════════════════════════════════════════
{
  const s = slide();
  sectionLabel(s, "Traction");
  title(s, "Shipped infrastructure—not a slideware concept.");

  const stats = [
    { n: "Live", l: "Product on Arc testnet rails" },
    { n: "Escrow", l: "Dual-lock BoardmanEscrow path" },
    { n: "Agents", l: "GM-strength hybrid Stockfish" },
    { n: "Open", l: "Public repo + builder stack" },
  ];
  stats.forEach((st, i) => {
    const x = 0.7 + i * 3.15;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.55, w: 3.0, h: 1.9, fill: { color: C.card }, shadow: sh(),
    });
    s.addText(st.n, {
      x: x + 0.2, y: 1.9, w: 2.6, h: 0.55,
      fontSize: 26, fontFace: FONT.h, color: C.accentSoft, bold: true, margin: 0, align: "center",
    });
    s.addText(st.l, {
      x: x + 0.2, y: 2.6, w: 2.6, h: 0.55,
      fontSize: 12, fontFace: FONT.b, color: C.muted, margin: 0, align: "center",
    });
  });

  s.addText("Public links", {
    x: 0.7, y: 3.8, w: 12, h: 0.35,
    fontSize: 14, fontFace: FONT.h, color: C.text, bold: true, margin: 0,
  });
  const links = [
    "boardman.playingsidequest.fun/agentic/arena.html",
    "github.com/playingsidequest-dotplay/boardman",
    "t.me/myboardmanOfficialBot",
  ];
  links.forEach((ln, i) => {
    s.addText(ln, {
      x: 0.7, y: 4.3 + i * 0.45, w: 12, h: 0.4,
      fontSize: 14, fontFace: FONT.b, color: C.muted, margin: 0,
    });
  });
  footer(s, 10);
}

// ═══════════════════════════════════════════════════════════════════
// 11. ROADMAP
// ═══════════════════════════════════════════════════════════════════
{
  const s = slide();
  sectionLabel(s, "Roadmap");
  title(s, "From testnet truth to mainnet markets.");

  const phases = [
    { p: "Now", t: "Testnet product", d: "Human dual-lock, agent arena, spectator books, LP accounting, public stack." },
    { p: "Next", t: "Hardening", d: "Anti-collusion, sybil limits on books, production deposits (no faucet), ops tooling." },
    { p: "Then", t: "Mainnet Arc", d: "BoardmanEscrow mainnet, Circle wallet UX, scaled agent deploy for third parties." },
    { p: "Later", t: "Multi-game markets", d: "Catalog expansion, partner game centers, optional CCTP funding paths." },
  ];
  phases.forEach((ph, i) => {
    const x = 0.7 + i * 3.15;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.7, w: 3.0, h: 4.3, fill: { color: C.card }, shadow: sh(),
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.7, w: 3.0, h: 0.12, fill: { color: i === 0 ? C.green : C.accent },
    });
    s.addText(ph.p.toUpperCase(), {
      x: x + 0.25, y: 2.15, w: 2.5, h: 0.3,
      fontSize: 11, fontFace: FONT.b, color: i === 0 ? C.green : C.accentSoft, bold: true, margin: 0, charSpacing: 1.5,
    });
    s.addText(ph.t, {
      x: x + 0.25, y: 2.65, w: 2.5, h: 0.85,
      fontSize: 18, fontFace: FONT.h, color: C.text, bold: true, margin: 0,
    });
    s.addText(ph.d, {
      x: x + 0.25, y: 3.7, w: 2.5, h: 1.9,
      fontSize: 13, fontFace: FONT.b, color: C.muted, margin: 0,
    });
  });
  footer(s, 11);
}

// ═══════════════════════════════════════════════════════════════════
// 12. CLOSE / ASK
// ═══════════════════════════════════════════════════════════════════
{
  const s = slide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.18, h: 7.5, fill: { color: C.accent },
  });
  s.addText("THE ASK", {
    x: 0.9, y: 1.4, w: 11, h: 0.3,
    fontSize: 12, fontFace: FONT.b, color: C.accentSoft, bold: true, margin: 0, charSpacing: 2,
  });
  s.addText("Build the settlement standard\nfor skill—on Arc.", {
    x: 0.9, y: 1.9, w: 11.5, h: 1.4,
    fontSize: 34, fontFace: FONT.h, color: C.white, bold: true, margin: 0,
  });
  s.addText("We are submitting under both tracks: DeFi (escrow, fees, capital rails) and Agentic Economy (autonomous agents, markets, creator & LP incentives).", {
    x: 0.9, y: 3.5, w: 11, h: 0.8,
    fontSize: 15, fontFace: FONT.b, color: C.muted, margin: 0,
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.9, y: 4.6, w: 5.5, h: 1.5, fill: { color: C.card }, shadow: sh(),
  });
  s.addText("Live", {
    x: 1.15, y: 4.85, w: 5, h: 0.3,
    fontSize: 12, fontFace: FONT.b, color: C.dim, bold: true, margin: 0, charSpacing: 1,
  });
  s.addText("boardman.playingsidequest.fun", {
    x: 1.15, y: 5.25, w: 5, h: 0.5,
    fontSize: 15, fontFace: FONT.b, color: C.accentSoft, margin: 0,
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.7, y: 4.6, w: 5.7, h: 1.5, fill: { color: C.card }, shadow: sh(),
  });
  s.addText("Code", {
    x: 6.95, y: 4.85, w: 5.2, h: 0.3,
    fontSize: 12, fontFace: FONT.b, color: C.dim, bold: true, margin: 0, charSpacing: 1,
  });
  s.addText("github.com/playingsidequest-dotplay/boardman", {
    x: 6.95, y: 5.25, w: 5.2, h: 0.5,
    fontSize: 14, fontFace: FONT.b, color: C.accentSoft, margin: 0,
  });

  s.addText("sideQuest  ·  Boardman", {
    x: 0.9, y: 6.5, w: 11, h: 0.3,
    fontSize: 13, fontFace: FONT.b, color: C.dim, margin: 0,
  });
}

const out = path.join(__dirname, "Boardman_Arc_Hackathon.pptx");
const pub = path.join(__dirname, "..", "frontend", "public", "demos", "Boardman_Arc_Hackathon.pptx");
pres.writeFile({ fileName: out }).then(() => {
  fs.copyFileSync(out, pub);
  console.log("Wrote", out);
  console.log("Copied", pub);
});
