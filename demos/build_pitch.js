/**
 * Boardman — Encode / Arc pitch deck
 * Humans (Telegram) + Agents (Stack) on the same USDC settlement rails.
 */
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const pres = new pptxgen();
pres.defineLayout({ name: "WIDE", width: 13.333, height: 7.5 });
pres.layout = "WIDE";
pres.author = "sideQuest";
pres.title = "Boardman — Pitch Deck";
pres.subject = "Encode Arc · DeFi + Agentic Economy";

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
const TOTAL = 12;

function sh() {
  return { type: "outer", color: "000000", blur: 18, offset: 4, angle: 135, opacity: 0.35 };
}
function slide() {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  return s;
}
function footer(s, page) {
  s.addText("BOARDMAN", {
    x: 0.6, y: 7.1, w: 3, h: 0.25,
    fontSize: 10, fontFace: FONT.b, color: C.dim, margin: 0, bold: true, charSpacing: 1.5,
  });
  s.addText("sideQuest  ·  Encode Arc", {
    x: 4.5, y: 7.1, w: 4.5, h: 0.25,
    fontSize: 10, fontFace: FONT.b, color: C.dim, margin: 0, align: "center",
  });
  s.addText(page + " / " + TOTAL, {
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
    fontSize: 30, fontFace: FONT.h, color: C.text, bold: true, margin: 0,
  });
}

// 1 TITLE
{
  const s = slide();
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.18, h: 7.5, fill: { color: C.accent } });
  s.addText("ENCODE  ·  ARC PROGRAMMABLE MONEY  ·  2026", {
    x: 0.9, y: 1.4, w: 11, h: 0.3,
    fontSize: 12, fontFace: FONT.b, color: C.accentSoft, bold: true, margin: 0, charSpacing: 2,
  });
  s.addText("Boardman", {
    x: 0.9, y: 1.95, w: 11, h: 0.85,
    fontSize: 52, fontFace: FONT.h, color: C.white, bold: true, margin: 0,
  });
  s.addText("Programmable USDC settlement for skill contests—\nhumans in Telegram, agents on Boardman Stack.", {
    x: 0.9, y: 2.95, w: 11, h: 0.95,
    fontSize: 20, fontFace: FONT.b, color: C.muted, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.9, y: 4.2, w: 2.0, h: 0.06, fill: { color: C.accent } });
  s.addText("DeFi Track  +  Agentic Economy Track", {
    x: 0.9, y: 4.5, w: 10, h: 0.35,
    fontSize: 15, fontFace: FONT.b, color: C.cyan, margin: 0, bold: true,
  });
  s.addText("sideQuest  ·  boardman.playingsidequest.fun  ·  t.me/myboardmanOfficialBot", {
    x: 0.9, y: 6.2, w: 11.5, h: 0.35,
    fontSize: 13, fontFace: FONT.b, color: C.dim, margin: 0,
  });
}

// 2 PROBLEM
{
  const s = slide();
  sectionLabel(s, "The problem");
  title(s, "Skill capital is huge. Settlement is broken.");
  s.addText("Friends already stake console, mobile, and local games. Money sits in chat apps, cash, or trust. Agents can play—but have no bankroll economy.", {
    x: 0.7, y: 1.4, w: 12, h: 0.65,
    fontSize: 15, fontFace: FONT.b, color: C.muted, margin: 0,
  });
  const problems = [
    { n: "01", t: "Human stakes are informal", d: "IOUs and group-chat “hold my money.” Disputes are social. No dual-lock, no proof, no compound capital." },
    { n: "02", t: "Crypto UX kills play", d: "Seed phrases, gas tokens, bridges. Mainstream players drop before the first match locks." },
    { n: "03", t: "Agents aren’t economic actors", d: "AI can move pieces. Without wallets, policy, fees, and markets, agents can’t join an economy." },
  ];
  problems.forEach((p, i) => {
    const x = 0.7 + i * 4.15;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 2.3, w: 3.95, h: 3.9, fill: { color: C.card }, shadow: sh() });
    s.addText(p.n, { x: x + 0.3, y: 2.6, w: 3.3, h: 0.4, fontSize: 20, fontFace: FONT.h, color: C.accent, bold: true, margin: 0 });
    s.addText(p.t, { x: x + 0.3, y: 3.2, w: 3.3, h: 0.75, fontSize: 17, fontFace: FONT.h, color: C.text, bold: true, margin: 0 });
    s.addText(p.d, { x: x + 0.3, y: 4.15, w: 3.3, h: 1.7, fontSize: 14, fontFace: FONT.b, color: C.muted, margin: 0 });
  });
  footer(s, 2);
}

// 3 SOLUTION
{
  const s = slide();
  sectionLabel(s, "The solution");
  title(s, "One settlement layer. Two ways to play.");
  s.addText("Boardman is programmable money for finite-outcome skill contests on Arc (USDC). Same dual-lock primitive for humans and agents.", {
    x: 0.7, y: 1.35, w: 12, h: 0.55, fontSize: 15, fontFace: FONT.b, color: C.muted, margin: 0,
  });

  s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y: 2.15, w: 5.85, h: 4.25, fill: { color: C.card }, shadow: sh() });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y: 2.15, w: 0.12, h: 4.25, fill: { color: C.cyan } });
  s.addText("HUMANS  ·  TELEGRAM", {
    x: 1.15, y: 2.4, w: 5, h: 0.3, fontSize: 12, fontFace: FONT.b, color: C.cyan, bold: true, margin: 0, charSpacing: 1.2,
  });
  s.addText("Human ↔ human skill", {
    x: 1.15, y: 2.8, w: 5, h: 0.4, fontSize: 20, fontFace: FONT.h, color: C.text, bold: true, margin: 0,
  });
  s.addText([
    { text: "Official bot + community group", options: { bullet: true, breakLine: true } },
    { text: "Public challenges — claim open matches", options: { bullet: true, breakLine: true } },
    { text: "Private 1v1s — challenge a friend", options: { bullet: true, breakLine: true } },
    { text: "Dual-lock USDC · play · AI proof · settle", options: { bullet: true } },
  ], { x: 1.15, y: 3.4, w: 5, h: 2.6, fontSize: 14, fontFace: FONT.b, color: C.muted, paraSpaceAfter: 8 });

  s.addShape(pres.shapes.RECTANGLE, { x: 6.8, y: 2.15, w: 5.85, h: 4.25, fill: { color: C.card }, shadow: sh() });
  s.addShape(pres.shapes.RECTANGLE, { x: 6.8, y: 2.15, w: 0.12, h: 4.25, fill: { color: C.accent } });
  s.addText("AGENTS  ·  BOARDMAN STACK", {
    x: 7.25, y: 2.4, w: 5, h: 0.3, fontSize: 12, fontFace: FONT.b, color: C.accentSoft, bold: true, margin: 0, charSpacing: 1.2,
  });
  s.addText("Autonomous economy", {
    x: 7.25, y: 2.8, w: 5, h: 0.4, fontSize: 20, fontFace: FONT.h, color: C.text, bold: true, margin: 0,
  });
  s.addText([
    { text: "Agents with bankrolls & policies", options: { bullet: true, breakLine: true } },
    { text: "Negotiated equal skill stakes", options: { bullet: true, breakLine: true } },
    { text: "Creator fees · LPs · spectator pots", options: { bullet: true, breakLine: true } },
    { text: "Builder stack: manifests + webhooks", options: { bullet: true } },
  ], { x: 7.25, y: 3.4, w: 5, h: 2.6, fontSize: 14, fontFace: FONT.b, color: C.muted, paraSpaceAfter: 8 });
  footer(s, 3);
}

// 4 HUMAN TELEGRAM (NEW FOCUS)
{
  const s = slide();
  sectionLabel(s, "Human layer");
  title(s, "Telegram is the boardroom.");
  s.addText("Where skill stakes already live — chat. Boardman turns that into dual-lock USDC, without forcing a new app install.", {
    x: 0.7, y: 1.35, w: 12, h: 0.5, fontSize: 14, fontFace: FONT.b, color: C.muted, margin: 0,
  });

  const flows = [
    { t: "Fund", d: "Open bot → Get USDC → fund wallet (testnet faucet path live)." },
    { t: "Public room", d: "Community group + live rooms. Post an open challenge; others claim (fastest fingers)." },
    { t: "Private 1v1", d: "Challenge a friend by Telegram identity. Accept → both dual-lock." },
    { t: "Play", d: "Console / real skill game offline. Submit full-time photo proof." },
    { t: "Settle", d: "AI-assisted outcome → BoardmanEscrow pays winner in USDC." },
  ];
  flows.forEach((f, i) => {
    const x = 0.55 + i * 2.5;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 2.1, w: 2.35, h: 3.5, fill: { color: C.card }, shadow: sh() });
    s.addShape(pres.shapes.OVAL, { x: x + 0.85, y: 2.35, w: 0.55, h: 0.55, fill: { color: C.cyan } });
    s.addText(String(i + 1), {
      x: x + 0.85, y: 2.42, w: 0.55, h: 0.45,
      fontSize: 16, fontFace: FONT.h, color: C.bg, bold: true, align: "center", margin: 0,
    });
    s.addText(f.t, {
      x: x + 0.15, y: 3.15, w: 2.05, h: 0.45,
      fontSize: 15, fontFace: FONT.h, color: C.text, bold: true, align: "center", margin: 0,
    });
    s.addText(f.d, {
      x: x + 0.15, y: 3.7, w: 2.05, h: 1.6,
      fontSize: 12, fontFace: FONT.b, color: C.muted, align: "center", margin: 0,
    });
  });
  s.addText("Bot: t.me/myboardmanOfficialBot   ·   Community / public challenges live in Telegram group", {
    x: 0.7, y: 5.9, w: 12, h: 0.35,
    fontSize: 13, fontFace: FONT.b, color: C.accentSoft, margin: 0,
  });
  footer(s, 4);
}

// 5 AGENT LAYER
{
  const s = slide();
  sectionLabel(s, "Agent layer");
  title(s, "Agents that hold capital—and risk it.");
  const cards = [
    { t: "Bankroll policy", d: "Max stake, reserve, seed bps. Whale vs lean agent → equal stake from free capital." },
    { t: "Skill ≠ spectator", d: "Dual-lock skill pot separate from fan book. One match_id, two ledgers." },
    { t: "Creators & LPs", d: "Creator fee on wins. LPs top up bankroll for a share of net skill profit." },
    { t: "Reference agents", d: "Raja (attack) vs Nero (defense). Stockfish + strategy; optional free LLM plus." },
  ];
  cards.forEach((c, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.7 + col * 6.25, y = 1.55 + row * 2.4;
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 6.0, h: 2.2, fill: { color: C.card }, shadow: sh() });
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.1, h: 2.2, fill: { color: i % 2 ? C.cyan : C.accent } });
    s.addText(c.t, { x: x + 0.4, y: y + 0.35, w: 5.3, h: 0.45, fontSize: 18, fontFace: FONT.h, color: C.text, bold: true, margin: 0 });
    s.addText(c.d, { x: x + 0.4, y: y + 1.0, w: 5.3, h: 0.85, fontSize: 14, fontFace: FONT.b, color: C.muted, margin: 0 });
  });
  footer(s, 5);
}

// 6 PRODUCT SURFACE
{
  const s = slide();
  sectionLabel(s, "Product surface");
  title(s, "What judges can open today.");
  const products = [
    { k: "01", t: "Telegram Boardman", s: "Humans", d: "Bot + community group. Public challenges, private friend 1v1s, dual-lock, proof, settle." },
    { k: "02", t: "Agent Arena", s: "Agents", d: "Live Raja vs Nero, spectator bets, creator desk, LP, negotiated stake." },
    { k: "03", t: "Boardman Stack", s: "Builders", d: "Register agents, webhooks, multi-game catalog, economy APIs, developer docs." },
  ];
  products.forEach((p, i) => {
    const y = 1.5 + i * 1.6;
    s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y, w: 12, h: 1.45, fill: { color: C.card }, shadow: sh() });
    s.addText(p.k, { x: 1.0, y: y + 0.4, w: 1.0, h: 0.55, fontSize: 22, fontFace: FONT.h, color: C.accent, bold: true, margin: 0 });
    s.addText(p.t, { x: 2.2, y: y + 0.28, w: 6.5, h: 0.4, fontSize: 20, fontFace: FONT.h, color: C.text, bold: true, margin: 0 });
    s.addText(p.s.toUpperCase(), {
      x: 9.3, y: y + 0.32, w: 3.0, h: 0.35,
      fontSize: 11, fontFace: FONT.b, color: C.accentSoft, bold: true, margin: 0, align: "right", charSpacing: 1,
    });
    s.addText(p.d, { x: 2.2, y: y + 0.8, w: 10, h: 0.4, fontSize: 14, fontFace: FONT.b, color: C.muted, margin: 0 });
  });
  footer(s, 6);
}

// 7 MONEY ARCHITECTURE
{
  const s = slide();
  sectionLabel(s, "Architecture");
  title(s, "Two money rails. Never mixed.");
  s.addText("Skill escrow defines the contest. Spectator markets are a side book. Humans and agents both dual-lock skill USDC.", {
    x: 0.7, y: 1.35, w: 12, h: 0.5, fontSize: 14, fontFace: FONT.b, color: C.muted, margin: 0,
  });
  const steps = [
    { t: "Fund", d: "Player wallet\nor agent bankroll\n(+ optional LP)" },
    { t: "Challenge", d: "Public claim\nor private accept\n(Telegram / API)" },
    { t: "Lock", d: "BoardmanEscrow\ndual-lock skill\nUSDC on Arc" },
    { t: "Play", d: "Human skill or\nautonomous\nagent match" },
    { t: "Settle", d: "Proof / outcome\nfees · payout\nrun it back" },
  ];
  steps.forEach((st, i) => {
    const x = 0.55 + i * 2.55;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 2.15, w: 2.35, h: 3.0, fill: { color: C.card }, shadow: sh() });
    s.addShape(pres.shapes.OVAL, { x: x + 0.85, y: 2.4, w: 0.55, h: 0.55, fill: { color: C.accent } });
    s.addText(String(i + 1), {
      x: x + 0.85, y: 2.48, w: 0.55, h: 0.45,
      fontSize: 16, fontFace: FONT.h, color: C.white, bold: true, align: "center", margin: 0,
    });
    s.addText(st.t, {
      x: x + 0.15, y: 3.15, w: 2.05, h: 0.4,
      fontSize: 16, fontFace: FONT.h, color: C.text, bold: true, align: "center", margin: 0,
    });
    s.addText(st.d, {
      x: x + 0.15, y: 3.65, w: 2.05, h: 1.2,
      fontSize: 12, fontFace: FONT.b, color: C.muted, align: "center", margin: 0,
    });
  });
  s.addText("Hard rule: skill escrow ≠ spectator pot. Same match. Separate ledgers. One outcome.", {
    x: 0.7, y: 5.5, w: 12, h: 0.4,
    fontSize: 13, fontFace: FONT.b, color: C.accentSoft, italic: true, margin: 0,
  });
  footer(s, 7);
}

// 8 ECONOMICS
{
  const s = slide();
  sectionLabel(s, "Economics");
  title(s, "Transparent take across roles.");
  const fees = [
    { rail: "Skill escrow (platform)", rate: "3%", note: "Aligned with BoardmanEscrow dual-lock pot" },
    { rail: "Creator skill fee", rate: "3–10%", note: "Of winner gross; set at agent deploy; capped" },
    { rail: "Spectator pot", rate: "~5%", note: "Side book: platform + creator pool" },
    { rail: "LP share", rate: "Policy", note: "Share of net skill profit for bankroll backers" },
  ];
  s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y: 1.5, w: 12, h: 0.5, fill: { color: C.bgAlt } });
  s.addText("RAIL", { x: 1.0, y: 1.58, w: 3.5, h: 0.35, fontSize: 11, bold: true, color: C.dim, margin: 0 });
  s.addText("RATE", { x: 4.6, y: 1.58, w: 1.8, h: 0.35, fontSize: 11, bold: true, color: C.dim, margin: 0 });
  s.addText("NOTES", { x: 6.6, y: 1.58, w: 5.8, h: 0.35, fontSize: 11, bold: true, color: C.dim, margin: 0 });
  fees.forEach((f, i) => {
    const y = 2.1 + i * 0.9;
    s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y, w: 12, h: 0.8, fill: { color: i % 2 ? C.card : C.bgAlt } });
    s.addText(f.rail, { x: 1.0, y: y + 0.22, w: 3.5, h: 0.4, fontSize: 15, bold: true, color: C.text, margin: 0 });
    s.addText(f.rate, { x: 4.6, y: y + 0.22, w: 1.8, h: 0.4, fontSize: 15, bold: true, color: C.accentSoft, margin: 0 });
    s.addText(f.note, { x: 6.6, y: y + 0.22, w: 5.8, h: 0.4, fontSize: 13, color: C.muted, margin: 0 });
  });
  footer(s, 8);
}

// 9 WHY ARC
{
  const s = slide();
  sectionLabel(s, "Why Arc");
  title(s, "Stablecoin settlement is the product.");
  const why = [
    { t: "USDC as unit of account", d: "Stakes, seeds, fees, pots — stable value matching how skill markets already price risk." },
    { t: "Consumer + agent UX", d: "No “find gas ETH first” drop-off. Telegram humans and autonomous loops need predictable settlement." },
    { t: "Programmable policy", d: "Escrow, free capital, seed bps, pot caps, creator fees are code — not group-chat convention." },
    { t: "One chain story", d: "Humans and agents share the dual-lock primitive on Arc testnet today; mainnet path is clear." },
  ];
  why.forEach((w, i) => {
    const y = 1.45 + i * 1.2;
    s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y, w: 12, h: 1.05, fill: { color: C.card }, shadow: sh() });
    s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y, w: 0.12, h: 1.05, fill: { color: C.accent } });
    s.addText(w.t, { x: 1.15, y: y + 0.15, w: 11.2, h: 0.35, fontSize: 16, fontFace: FONT.h, color: C.text, bold: true, margin: 0 });
    s.addText(w.d, { x: 1.15, y: y + 0.55, w: 11.2, h: 0.35, fontSize: 13, fontFace: FONT.b, color: C.muted, margin: 0 });
  });
  footer(s, 9);
}

// 10 TRACTION
{
  const s = slide();
  sectionLabel(s, "Shipped");
  title(s, "Live rails—not slideware.");
  const stats = [
    { n: "Telegram", l: "Bot + community challenges" },
    { n: "Escrow", l: "BoardmanEscrow dual-lock Arc" },
    { n: "Arena", l: "Agents · bets · creator desk" },
    { n: "Stack", l: "Public repo + builder docs" },
  ];
  stats.forEach((st, i) => {
    const x = 0.7 + i * 3.15;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 1.5, w: 3.0, h: 1.85, fill: { color: C.card }, shadow: sh() });
    s.addText(st.n, {
      x: x + 0.15, y: 1.85, w: 2.7, h: 0.5,
      fontSize: 20, fontFace: FONT.h, color: C.accentSoft, bold: true, margin: 0, align: "center",
    });
    s.addText(st.l, {
      x: x + 0.15, y: 2.5, w: 2.7, h: 0.55,
      fontSize: 12, fontFace: FONT.b, color: C.muted, margin: 0, align: "center",
    });
  });
  s.addText("Open these", {
    x: 0.7, y: 3.7, w: 12, h: 0.35, fontSize: 14, fontFace: FONT.h, color: C.text, bold: true, margin: 0,
  });
  [
    "t.me/myboardmanOfficialBot",
    "boardman.playingsidequest.fun/agentic/arena.html",
    "github.com/playingsidequest-dotplay/boardman",
  ].forEach((ln, i) => {
    s.addText(ln, {
      x: 0.7, y: 4.2 + i * 0.45, w: 12, h: 0.4,
      fontSize: 15, fontFace: FONT.b, color: C.muted, margin: 0,
    });
  });
  footer(s, 10);
}

// 11 ROADMAP
{
  const s = slide();
  sectionLabel(s, "Roadmap");
  title(s, "Testnet truth → mainnet markets.");
  const phases = [
    { p: "Now", t: "Testnet product", d: "Telegram humans, agent arena, spectator books, LP accounting, public stack." },
    { p: "Next", t: "Hardening", d: "Anti-abuse on public rooms, production deposits, ops tooling, better proof UX." },
    { p: "Then", t: "Mainnet Arc", d: "BoardmanEscrow mainnet, Circle wallet UX, third-party agent deploy at scale." },
    { p: "Later", t: "Multi-game markets", d: "Catalog + partner game centers; optional multi-rail funding." },
  ];
  phases.forEach((ph, i) => {
    const x = 0.7 + i * 3.15;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 1.65, w: 3.0, h: 4.35, fill: { color: C.card }, shadow: sh() });
    s.addShape(pres.shapes.RECTANGLE, { x, y: 1.65, w: 3.0, h: 0.12, fill: { color: i === 0 ? C.green : C.accent } });
    s.addText(ph.p.toUpperCase(), {
      x: x + 0.25, y: 2.1, w: 2.5, h: 0.3,
      fontSize: 11, fontFace: FONT.b, color: i === 0 ? C.green : C.accentSoft, bold: true, margin: 0, charSpacing: 1.5,
    });
    s.addText(ph.t, {
      x: x + 0.25, y: 2.6, w: 2.5, h: 0.85,
      fontSize: 18, fontFace: FONT.h, color: C.text, bold: true, margin: 0,
    });
    s.addText(ph.d, {
      x: x + 0.25, y: 3.65, w: 2.5, h: 1.9,
      fontSize: 13, fontFace: FONT.b, color: C.muted, margin: 0,
    });
  });
  footer(s, 11);
}

// 12 ASK
{
  const s = slide();
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.18, h: 7.5, fill: { color: C.accent } });
  s.addText("THE ASK", {
    x: 0.9, y: 1.35, w: 11, h: 0.3,
    fontSize: 12, fontFace: FONT.b, color: C.accentSoft, bold: true, margin: 0, charSpacing: 2,
  });
  s.addText("Settle skill—human and agent—\non Arc with Boardman.", {
    x: 0.9, y: 1.85, w: 11.5, h: 1.35,
    fontSize: 32, fontFace: FONT.h, color: C.white, bold: true, margin: 0,
  });
  s.addText("Submitting DeFi (escrow, fees, capital rails) and Agentic Economy (autonomous agents, markets, creators & LPs). Accelerator: scale Telegram rooms + agent stack with Encode network.", {
    x: 0.9, y: 3.4, w: 11.2, h: 0.85,
    fontSize: 15, fontFace: FONT.b, color: C.muted, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.9, y: 4.5, w: 5.5, h: 1.45, fill: { color: C.card }, shadow: sh() });
  s.addText("Live", { x: 1.15, y: 4.7, w: 5, h: 0.28, fontSize: 12, color: C.dim, bold: true, margin: 0 });
  s.addText("boardman.playingsidequest.fun\nt.me/myboardmanOfficialBot", {
    x: 1.15, y: 5.1, w: 5, h: 0.65, fontSize: 14, color: C.accentSoft, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, { x: 6.7, y: 4.5, w: 5.7, h: 1.45, fill: { color: C.card }, shadow: sh() });
  s.addText("Code", { x: 6.95, y: 4.7, w: 5.2, h: 0.28, fontSize: 12, color: C.dim, bold: true, margin: 0 });
  s.addText("github.com/playingsidequest-dotplay/boardman", {
    x: 6.95, y: 5.15, w: 5.2, h: 0.45, fontSize: 13, color: C.accentSoft, margin: 0,
  });
  s.addText("sideQuest  ·  Boardman", {
    x: 0.9, y: 6.35, w: 11, h: 0.3, fontSize: 13, color: C.dim, margin: 0,
  });
}

const out = path.join(__dirname, "Boardman_Arc_Hackathon.pptx");
const pub = path.join(__dirname, "..", "frontend", "public", "demos", "Boardman_Arc_Hackathon.pptx");
pres.writeFile({ fileName: out }).then(() => {
  fs.mkdirSync(path.dirname(pub), { recursive: true });
  fs.copyFileSync(out, pub);
  console.log("Wrote", out);
  console.log("Copied", pub);
});
