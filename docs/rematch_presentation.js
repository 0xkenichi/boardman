// Rematch by sideQuest — brand presentation deck
// Run: node docs/rematch_presentation.js
// Output: docs/Rematch_by_sideQuest.pptx

const pptxgen = require("pptxgenjs");
const path = require("path");

// ---------- Brand tokens (from rematch logo + BRAND_REMATCH.md) ----------
const COLOR_BG      = "0A0A0A"; // near-black
const COLOR_CARD    = "141414"; // elevated surface
const COLOR_TEXT    = "F5F5F0"; // warm off-white
const COLOR_MUTED   = "6B6B6B";
const COLOR_MUTED_2 = "8A8A8A";
const COLOR_ACCENT  = "229C68"; // logo green
const COLOR_ACCENT2 = "2ECB82"; // lighter green for highlights
const COLOR_DIV     = "2A2A2A";
const COLOR_BLACK   = "0A0A0A";
const COLOR_STRIKE  = "555555";

const FONT_HEAD = "Arial";
const FONT_BODY = "Calibri";

const SLIDE_W = 13.333;
const SLIDE_H = 7.5;
const MARGIN  = 0.6;
const TOTAL   = 13;

const LOGO = path.join(__dirname, "../frontend/public/rematch-logo.png");

// ---------- Chrome ----------
function addTopBar(slide, sectionLabel) {
  slide.addText("REMATCH", {
    x: MARGIN, y: 0.4, w: 3.0, h: 0.4,
    fontFace: FONT_HEAD, fontSize: 13, bold: true,
    color: COLOR_TEXT, charSpacing: 4,
    align: "left", valign: "middle", margin: 0, wrap: false,
  });
  if (sectionLabel) {
    slide.addText(sectionLabel, {
      x: SLIDE_W - MARGIN - 5.0, y: 0.4, w: 5.0, h: 0.4,
      fontFace: FONT_HEAD, fontSize: 11,
      color: COLOR_MUTED_2, charSpacing: 2,
      align: "right", valign: "middle", margin: 0,
    });
  }
}

function addFooter(slide, leftText, pageNum) {
  if (leftText) {
    slide.addText(leftText, {
      x: MARGIN, y: SLIDE_H - 0.55, w: 8.0, h: 0.3,
      fontFace: FONT_HEAD, fontSize: 10,
      color: COLOR_MUTED, charSpacing: 2,
      align: "left", valign: "middle", margin: 0,
    });
  }
  slide.addText(`REMATCH  ·  SIDEQUEST  ·  ${String(pageNum).padStart(2, "0")} / ${String(TOTAL).padStart(2, "0")}`, {
    x: SLIDE_W - MARGIN - 5.5, y: SLIDE_H - 0.55, w: 5.5, h: 0.3,
    fontFace: FONT_HEAD, fontSize: 10,
    color: COLOR_MUTED, charSpacing: 2,
    align: "right", valign: "middle", margin: 0,
  });
}

function sectionLabel(slide, label, y = 1.2) {
  slide.addText(label, {
    x: MARGIN, y, w: 10, h: 0.32,
    fontFace: FONT_HEAD, fontSize: 11, color: COLOR_MUTED_2,
    charSpacing: 3, margin: 0, valign: "middle",
  });
}

// ============================================================
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "Rematch by sideQuest";
pres.author = "sideQuest";
pres.subject = "Lock in. Play. Rematch.";
pres.company = "sideQuest";

// ------------------------------------------------------------
// 01 — Cover
// ------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: COLOR_BG };

  s.addText("REMATCH  ·  BY SIDEQUEST", {
    x: MARGIN, y: 0.4, w: 7, h: 0.4,
    fontFace: FONT_HEAD, fontSize: 12, bold: true,
    color: COLOR_TEXT, charSpacing: 3, margin: 0, wrap: false,
  });
  s.addText("LIVE  ·  TELEGRAM  ·  USDC", {
    x: SLIDE_W - MARGIN - 4.5, y: 0.4, w: 4.5, h: 0.4,
    fontFace: FONT_HEAD, fontSize: 12,
    color: COLOR_MUTED_2, charSpacing: 2, align: "right", margin: 0,
  });

  // Logo mark
  s.addImage({
    path: LOGO,
    x: MARGIN, y: 1.35, w: 1.15, h: 1.15,
    altText: "Rematch logo",
  });

  s.addText("LOCK IN. PLAY.\nREMATCH.", {
    x: MARGIN, y: 2.7, w: 11.5, h: 2.4,
    fontFace: FONT_HEAD, fontSize: 64, bold: true,
    color: COLOR_TEXT, margin: 0, valign: "top", charSpacing: -1,
  });

  // Accent underline bar under headline
  s.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN, y: 5.25, w: 2.2, h: 0.08,
    fill: { color: COLOR_ACCENT }, line: { color: COLOR_ACCENT, width: 0 },
  });

  s.addText("1v1 skill matches today  ·  multi-surface tomorrow  ·  Stack + home app ahead", {
    x: MARGIN, y: 5.5, w: 11.5, h: 0.4,
    fontFace: FONT_BODY, fontSize: 15, color: COLOR_MUTED_2, margin: 0,
  });

  s.addText("playingsidequest.fun/rematch", {
    x: MARGIN, y: SLIDE_H - 0.55, w: 6, h: 0.3,
    fontFace: FONT_HEAD, fontSize: 11, color: COLOR_ACCENT2, charSpacing: 1, margin: 0,
  });
  s.addText("01 / 13", {
    x: SLIDE_W - MARGIN - 2, y: SLIDE_H - 0.55, w: 2, h: 0.3,
    fontFace: FONT_HEAD, fontSize: 11, color: COLOR_MUTED, align: "right", margin: 0,
  });
}

// ------------------------------------------------------------
// 02 — What it is
// ------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: COLOR_BG };
  addTopBar(s, "02 / 13 — PRODUCT");
  sectionLabel(s, "WHAT IT IS");

  s.addText("Where console rivals\nsettle it.", {
    x: MARGIN, y: 1.55, w: 12, h: 1.35,
    fontFace: FONT_HEAD, fontSize: 42, bold: true,
    color: COLOR_TEXT, margin: 0, valign: "top",
  });

  s.addText(
    "Rematch is a Telegram app for 1v1 skill matches. Friends lock USDC, play (EA FC is the focus; more titles supported), prove the result with a full-time photo, and get paid — then run it back.",
    {
      x: MARGIN, y: 3.05, w: 11.5, h: 0.65,
      fontFace: FONT_BODY, fontSize: 16, color: COLOR_MUTED_2, margin: 0,
    }
  );
  s.addText(
    "Long-term: first app on Rematch Stack, a home app for every Stack experience + Rematch official, and surfaces on WhatsApp & Discord so players never have to come find us.",
    {
      x: MARGIN, y: 3.75, w: 11.5, h: 0.7,
      fontFace: FONT_BODY, fontSize: 15, color: COLOR_ACCENT2, margin: 0,
    }
  );

  // Three pillars
  const pillars = [
    { t: "SKILL", d: "Real matches.\nNot odds." },
    { t: "LOCK", d: "Both stake USDC.\nFair dual escrow." },
    { t: "PROOF", d: "AI reads the\nfull-time score." },
  ];
  pillars.forEach((p, i) => {
    const x = MARGIN + i * 4.1;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 4.65, w: 3.85, h: 1.55,
      fill: { color: COLOR_CARD }, line: { color: COLOR_DIV, width: 1 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 4.65, w: 0.1, h: 1.55,
      fill: { color: COLOR_ACCENT }, line: { color: COLOR_ACCENT, width: 0 },
    });
    s.addText(p.t, {
      x: x + 0.35, y: 4.8, w: 3.3, h: 0.35,
      fontFace: FONT_HEAD, fontSize: 14, bold: true, color: COLOR_ACCENT,
      charSpacing: 3, margin: 0,
    });
    s.addText(p.d, {
      x: x + 0.35, y: 5.2, w: 3.3, h: 0.8,
      fontFace: FONT_BODY, fontSize: 16, color: COLOR_TEXT, margin: 0,
    });
  });

  addFooter(s, "PRODUCT TODAY  ·  PLATFORM AHEAD  ·  SKILL SETTLEMENT", 2);
}

// ------------------------------------------------------------
// 03 — The problem
// ------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: COLOR_BG };
  addTopBar(s, "03 / 13 — PROBLEM");
  sectionLabel(s, "THE PROBLEM");

  s.addText([
    { text: "TRUST ME, I WON.", options: { strike: true, color: COLOR_STRIKE } },
  ], {
    x: MARGIN, y: 1.65, w: 12, h: 0.85,
    fontFace: FONT_HEAD, fontSize: 42, bold: true, margin: 0,
  });

  s.addText([
    { text: "PROVE IT. ", options: { color: COLOR_ACCENT } },
    { text: "SETTLE IT.", options: { color: COLOR_TEXT } },
  ], {
    x: MARGIN, y: 2.55, w: 12, h: 0.9,
    fontFace: FONT_HEAD, fontSize: 48, bold: true, margin: 0,
  });

  s.addText(
    "Friends play for pride and cash every night. Settling is messy: screenshots in DMs, disputes, no-shows, and someone holding the money. Rematch turns that chaos into a clear loop.",
    {
      x: MARGIN, y: 3.7, w: 11.5, h: 0.85,
      fontFace: FONT_BODY, fontSize: 17, color: COLOR_MUTED_2, margin: 0,
    }
  );

  const pains = [
    { n: "01", t: "No shared pot", d: "Someone has to hold the money — or nobody does." },
    { n: "02", t: "No neutral proof", d: "Score arguments live forever in group chats." },
    { n: "03", t: "No rematch loop", d: "Friction kills the \"one more game\" moment." },
  ];
  pains.forEach((p, i) => {
    const x = MARGIN + i * 4.1;
    s.addText(p.n, {
      x, y: 4.8, w: 3.8, h: 0.35,
      fontFace: FONT_HEAD, fontSize: 13, bold: true, color: COLOR_ACCENT, charSpacing: 2, margin: 0,
    });
    s.addText(p.t, {
      x, y: 5.2, w: 3.8, h: 0.4,
      fontFace: FONT_HEAD, fontSize: 18, bold: true, color: COLOR_TEXT, margin: 0,
    });
    s.addText(p.d, {
      x, y: 5.65, w: 3.8, h: 0.55,
      fontFace: FONT_BODY, fontSize: 14, color: COLOR_MUTED_2, margin: 0,
    });
  });

  addFooter(s, "SKILL MATCHES NEED FAIR RAILS", 3);
}

// ------------------------------------------------------------
// 04 — How it works
// ------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: COLOR_BG };
  addTopBar(s, "04 / 13 — FLOW");
  sectionLabel(s, "HOW IT WORKS");

  s.addText("Five steps. Zero drama.", {
    x: MARGIN, y: 1.55, w: 12, h: 0.55,
    fontFace: FONT_HEAD, fontSize: 32, bold: true, color: COLOR_TEXT, margin: 0,
  });

  const steps = [
    { n: "1", t: "Fund", d: "Open the bot.\nGet USDC in your\ncustodial wallet." },
    { n: "2", t: "Challenge", d: "Pick a friend,\nstake, and game.\nThey accept." },
    { n: "3", t: "Lock", d: "Both lock USDC.\nDual escrow.\nNo half-deals." },
    { n: "4", t: "Play", d: "HOME or AWAY.\nConsole match.\nReal skill." },
    { n: "5", t: "Settle", d: "FT photo in.\nAI reads score.\nWinner paid." },
  ];

  const gap = 0.22;
  const cardW = (SLIDE_W - MARGIN * 2 - gap * 4) / 5;
  const cardY = 2.4;
  const cardH = 3.7;

  steps.forEach((st, i) => {
    const x = MARGIN + i * (cardW + gap);
    const highlight = i === 4;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: cardY, w: cardW, h: cardH,
      fill: { color: highlight ? COLOR_ACCENT : COLOR_CARD },
      line: { color: highlight ? COLOR_ACCENT : COLOR_DIV, width: 1 },
    });
    s.addText(st.n, {
      x: x + 0.2, y: cardY + 0.3, w: cardW - 0.4, h: 0.55,
      fontFace: FONT_HEAD, fontSize: 36, bold: true,
      color: highlight ? COLOR_BLACK : COLOR_ACCENT, margin: 0,
    });
    s.addText(st.t.toUpperCase(), {
      x: x + 0.2, y: cardY + 1.1, w: cardW - 0.4, h: 0.45,
      fontFace: FONT_HEAD, fontSize: 16, bold: true,
      color: highlight ? COLOR_BLACK : COLOR_TEXT, charSpacing: 1, margin: 0,
    });
    s.addText(st.d, {
      x: x + 0.2, y: cardY + 1.7, w: cardW - 0.4, h: 1.7,
      fontFace: FONT_BODY, fontSize: 13,
      color: highlight ? "0A0A0A" : COLOR_MUTED_2, margin: 0,
    });
  });

  addFooter(s, "OPEN → ACCEPT → LOCK → PLAY → PROOF → PAYOUT → REMATCH", 4);
}

// ------------------------------------------------------------
// 05 — Fair by design
// ------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: COLOR_BG };
  addTopBar(s, "05 / 13 — FAIRNESS");
  sectionLabel(s, "FAIR BY DESIGN");

  s.addText("Trust is the product.", {
    x: MARGIN, y: 1.55, w: 12, h: 0.55,
    fontFace: FONT_HEAD, fontSize: 32, bold: true, color: COLOR_TEXT, margin: 0,
  });

  const fair = [
    {
      t: "Dual-lock escrow",
      d: "Both players lock USDC on-chain. Funds move only when the match resolves — not when one person says so.",
    },
    {
      t: "AI full-time proof",
      d: "Submit a full-time scoreline photo. Vision reads the result so the chat is not the referee.",
    },
    {
      t: "One match at a time",
      d: "Clear status, clear next action. No pile of open bets or confusing odds boards.",
    },
    {
      t: "Safety rails",
      d: "Stake caps, pause switches, rate limits, and dispute paths for edge cases.",
    },
  ];

  fair.forEach((f, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = MARGIN + col * 6.2;
    const y = 2.35 + row * 1.9;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 5.95, h: 1.7,
      fill: { color: COLOR_CARD }, line: { color: COLOR_DIV, width: 1 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 5.95, h: 0.08,
      fill: { color: COLOR_ACCENT }, line: { color: COLOR_ACCENT, width: 0 },
    });
    s.addText(f.t, {
      x: x + 0.35, y: y + 0.3, w: 5.3, h: 0.4,
      fontFace: FONT_HEAD, fontSize: 18, bold: true, color: COLOR_TEXT, margin: 0,
    });
    s.addText(f.d, {
      x: x + 0.35, y: y + 0.8, w: 5.3, h: 0.7,
      fontFace: FONT_BODY, fontSize: 14, color: COLOR_MUTED_2, margin: 0,
    });
  });

  addFooter(s, "SKILL MATCH → FAIR LOCK → PROOF → PAYOUT → REMATCH", 5);
}

// ------------------------------------------------------------
// 06 — For players
// ------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: COLOR_BG };
  addTopBar(s, "06 / 13 — PLAYERS");
  sectionLabel(s, "BUILT FOR PLAYERS");

  s.addText([
    { text: "Meet players\n", options: { color: COLOR_TEXT } },
    { text: "where they are.", options: { color: COLOR_ACCENT } },
  ], {
    x: MARGIN, y: 1.5, w: 6.5, h: 1.4,
    fontFace: FONT_HEAD, fontSize: 34, bold: true, margin: 0,
  });

  s.addText(
    "Telegram-native and button-first today. Public channel for open challenges and online matchups. WhatsApp and Discord next — so users don't have to come to us.",
    {
      x: MARGIN, y: 3.1, w: 6.2, h: 1.15,
      fontFace: FONT_BODY, fontSize: 15, color: COLOR_MUTED_2, margin: 0,
    }
  );
  s.addText(
    "No complex wallets first. No DeFi jargon. Challenge a friend the way you already chat.",
    {
      x: MARGIN, y: 4.35, w: 6.2, h: 0.7,
      fontFace: FONT_BODY, fontSize: 14, color: COLOR_MUTED_2, margin: 0,
    }
  );

  const menu = [
    ["My match", "Active match + actions"],
    ["New challenge", "Tag → stake → game → send"],
    ["Public board", "Open challenges · online rivals"],
    ["Wallet", "USDC + PLAY score"],
    ["How to play", "Rules in one tap"],
  ];

  const rightX = 7.4;
  const rightW = SLIDE_W - MARGIN - rightX;
  s.addShape(pres.shapes.RECTANGLE, {
    x: rightX, y: 1.5, w: rightW, h: 4.75,
    fill: { color: COLOR_CARD }, line: { color: COLOR_DIV, width: 1 },
  });
  s.addText("TODAY ON TELEGRAM", {
    x: rightX + 0.4, y: 1.7, w: rightW - 0.8, h: 0.35,
    fontFace: FONT_HEAD, fontSize: 12, bold: true, color: COLOR_ACCENT, charSpacing: 2, margin: 0,
  });

  menu.forEach((row, i) => {
    const y = 2.2 + i * 0.72;
    s.addShape(pres.shapes.LINE, {
      x: rightX + 0.4, y: y - 0.08, w: rightW - 0.8, h: 0,
      line: { color: COLOR_DIV, width: 0.75 },
    });
    s.addText(row[0], {
      x: rightX + 0.4, y, w: 2.4, h: 0.55,
      fontFace: FONT_HEAD, fontSize: 14, bold: true, color: COLOR_TEXT, margin: 0, valign: "middle",
    });
    s.addText(row[1], {
      x: rightX + 2.7, y, w: rightW - 3.2, h: 0.55,
      fontFace: FONT_BODY, fontSize: 13, color: COLOR_MUTED_2, margin: 0, valign: "middle",
    });
  });

  addFooter(s, "TELEGRAM NOW  ·  WHATSAPP + DISCORD AHEAD  ·  PUBLIC MATCHUPS", 6);
}

// ------------------------------------------------------------
// 07 — PLAY points
// ------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: COLOR_BG };
  addTopBar(s, "07 / 13 — PLAY");
  sectionLabel(s, "REPUTATION & REWARDS");

  s.addText([
    { text: "Play well. ", options: { color: COLOR_TEXT } },
    { text: "Earn PLAY.", options: { color: COLOR_ACCENT } },
  ], {
    x: MARGIN, y: 1.55, w: 12, h: 0.7,
    fontFace: FONT_HEAD, fontSize: 36, bold: true, margin: 0,
  });

  s.addText(
    "PLAY points reward good behaviour — finishing matches, showing up, competing fair. Points are a score and season weight, not a promise of tokens 1:1.",
    {
      x: MARGIN, y: 2.3, w: 12, h: 0.7,
      fontFace: FONT_BODY, fontSize: 16, color: COLOR_MUTED_2, margin: 0,
    }
  );

  // Two big cards
  s.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN, y: 3.25, w: 5.95, h: 2.85,
    fill: { color: COLOR_CARD }, line: { color: COLOR_DIV, width: 1 },
  });
  s.addText("PLAY POINTS", {
    x: MARGIN + 0.4, y: 3.5, w: 5.2, h: 0.35,
    fontFace: FONT_HEAD, fontSize: 12, bold: true, color: COLOR_ACCENT, charSpacing: 3, margin: 0,
  });
  s.addText("Off-chain score", {
    x: MARGIN + 0.4, y: 3.95, w: 5.2, h: 0.45,
    fontFace: FONT_HEAD, fontSize: 24, bold: true, color: COLOR_TEXT, margin: 0,
  });
  s.addText(
    "Earned by playing and finishing. Powers tiers, leaderboards, and season eligibility. Account-bound — not tradable.",
    {
      x: MARGIN + 0.4, y: 4.55, w: 5.2, h: 1.2,
      fontFace: FONT_BODY, fontSize: 15, color: COLOR_MUTED_2, margin: 0,
    }
  );

  s.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN + 6.2, y: 3.25, w: 5.95, h: 2.85,
    fill: { color: COLOR_ACCENT }, line: { color: COLOR_ACCENT, width: 0 },
  });
  s.addText("$PLAY TOKEN", {
    x: MARGIN + 6.6, y: 3.5, w: 5.2, h: 0.35,
    fontFace: FONT_HEAD, fontSize: 12, bold: true, color: COLOR_BLACK, charSpacing: 3, margin: 0,
  });
  s.addText("Later path", {
    x: MARGIN + 6.6, y: 3.95, w: 5.2, h: 0.45,
    fontFace: FONT_HEAD, fontSize: 24, bold: true, color: COLOR_BLACK, margin: 0,
  });
  s.addText(
    "On-chain token when seasons fund. Points weight airdrops — never claimed as 1:1. Honest by design.",
    {
      x: MARGIN + 6.6, y: 4.55, w: 5.2, h: 1.2,
      fontFace: FONT_BODY, fontSize: 15, color: COLOR_BLACK, margin: 0,
    }
  );

  addFooter(s, "POINTS ≠ TOKEN  ·  SEASONS SET THE RULES", 7);
}

// ------------------------------------------------------------
// 08 — Under the hood
// ------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: COLOR_BG };
  addTopBar(s, "08 / 13 — RAILS");
  sectionLabel(s, "UNDER THE HOOD");

  s.addText("Serious rails.\nSimple surface.", {
    x: MARGIN, y: 1.55, w: 12, h: 1.3,
    fontFace: FONT_HEAD, fontSize: 40, bold: true, color: COLOR_TEXT, margin: 0,
  });

  const rails = [
    { t: "Telegram", d: "Bot + button UX where players already are." },
    { t: "Circle wallets", d: "Developer-controlled USDC wallets. Easy fund & pay." },
    { t: "ClawEscrow", d: "Dual-lock / resolve smart contracts on testnets." },
    { t: "AI vision", d: "Full-time screenshot → structured scoreline." },
    { t: "Multi-chain", d: "Arc-first · Avalanche Fuji · Base Sepolia." },
    { t: "Safety", d: "Caps, pause switches, rate limits, disputes." },
  ];

  rails.forEach((item, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = MARGIN + col * 4.15;
    const y = 3.2 + row * 1.55;
    s.addText(String(i + 1).padStart(2, "0"), {
      x, y, w: 3.9, h: 0.3,
      fontFace: FONT_HEAD, fontSize: 12, bold: true, color: COLOR_ACCENT, charSpacing: 2, margin: 0,
    });
    s.addText(item.t, {
      x, y: y + 0.35, w: 3.9, h: 0.4,
      fontFace: FONT_HEAD, fontSize: 18, bold: true, color: COLOR_TEXT, margin: 0,
    });
    s.addText(item.d, {
      x, y: y + 0.8, w: 3.9, h: 0.55,
      fontFace: FONT_BODY, fontSize: 14, color: COLOR_MUTED_2, margin: 0,
    });
  });

  addFooter(s, "THESE RAILS POWER REMATCH — AND BECOME REMATCH STACK", 8);
}

// ------------------------------------------------------------
// 09 — Rematch Stack (platform vision)
// ------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: COLOR_BG };
  addTopBar(s, "09 / 13 — PLATFORM");
  sectionLabel(s, "THE LONG GAME");

  s.addText([
    { text: "Rematch Stack.", options: { color: COLOR_ACCENT } },
  ], {
    x: MARGIN, y: 1.45, w: 12, h: 0.5,
    fontFace: FONT_HEAD, fontSize: 30, bold: true, margin: 0,
  });

  s.addText(
    "The infrastructure that powers Rematch — exposed so other builders can create entirely new experiences on top.",
    {
      x: MARGIN, y: 2.0, w: 12, h: 0.45,
      fontFace: FONT_BODY, fontSize: 16, color: COLOR_TEXT, margin: 0,
    }
  );

  // Three layers
  const layers = [
    {
      label: "EXPERIENCES",
      title: "Apps & bots",
      body: "Rematch official +\nbuilder apps on Stack.\nOne home app later.",
    },
    {
      label: "PLATFORM",
      title: "Rematch Stack",
      body: "Wallets · escrow · matches\n· proof · PLAY · safety\n· multi-chain · webhooks.",
      hot: true,
    },
    {
      label: "RAILS",
      title: "Settlement",
      body: "Circle wallets.\nClawEscrow dual-lock.\nChains + data store.",
    },
  ];

  layers.forEach((L, i) => {
    const x = MARGIN + i * 4.15;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.6, w: 3.95, h: 2.35,
      fill: { color: L.hot ? COLOR_ACCENT : COLOR_CARD },
      line: { color: L.hot ? COLOR_ACCENT : COLOR_DIV, width: 1 },
    });
    s.addText(L.label, {
      x: x + 0.3, y: 2.75, w: 3.35, h: 0.28,
      fontFace: FONT_HEAD, fontSize: 11, bold: true,
      color: L.hot ? COLOR_BLACK : COLOR_ACCENT, charSpacing: 2, margin: 0,
    });
    s.addText(L.title, {
      x: x + 0.3, y: 3.1, w: 3.35, h: 0.38,
      fontFace: FONT_HEAD, fontSize: 18, bold: true,
      color: L.hot ? COLOR_BLACK : COLOR_TEXT, margin: 0,
    });
    s.addText(L.body, {
      x: x + 0.3, y: 3.55, w: 3.35, h: 1.15,
      fontFace: FONT_BODY, fontSize: 14,
      color: L.hot ? "0A0A0A" : COLOR_MUTED_2, margin: 0,
    });
  });

  // Hub app callout
  s.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN, y: 5.15, w: SLIDE_W - MARGIN * 2, h: 1.15,
    fill: { color: COLOR_CARD }, line: { color: COLOR_DIV, width: 1 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN, y: 5.15, w: 0.1, h: 1.15,
    fill: { color: COLOR_ACCENT }, line: { color: COLOR_ACCENT, width: 0 },
  });
  s.addText("THE HOME APP", {
    x: MARGIN + 0.35, y: 5.3, w: 11.5, h: 0.28,
    fontFace: FONT_HEAD, fontSize: 12, bold: true, color: COLOR_ACCENT, charSpacing: 2, margin: 0,
  });
  s.addText(
    "Long-run: one Rematch app that houses Rematch official and every app or bot built on Rematch Stack — discover, launch, play, settle in one place.",
    {
      x: MARGIN + 0.35, y: 5.65, w: 11.5, h: 0.45,
      fontFace: FONT_BODY, fontSize: 15, color: COLOR_TEXT, margin: 0,
    }
  );

  addFooter(s, "ONE MONEY PATH  ·  REMATCH OFFICIAL + BUILDER APPS UNDER ONE ROOF", 9);
}

// ------------------------------------------------------------
// 10 — Reach, games, livestream
// ------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: COLOR_BG };
  addTopBar(s, "10 / 13 — GROWTH");
  sectionLabel(s, "WHERE PLAY HAPPENS");

  s.addText("Expand the surface.\nKeep the settle.", {
    x: MARGIN, y: 1.45, w: 12, h: 1.15,
    fontFace: FONT_HEAD, fontSize: 32, bold: true, color: COLOR_TEXT, margin: 0,
  });

  const growth = [
    {
      n: "01",
      t: "Channels",
      d: "Telegram live. WhatsApp & Discord next — we go where users already are, so they don't have to come to us.",
    },
    {
      n: "02",
      t: "Games",
      d: "Other titles already fit the rails. Focus stays on EA FC. Mobile games landing soon.",
    },
    {
      n: "03",
      t: "Public matchups",
      d: "Public Telegram channel to pick up open challenges and online matchups — not only friend tags.",
    },
    {
      n: "04",
      t: "Livestream",
      d: "On the roadmap: stream the rivalry, pull spectators in, keep settlement fair underneath.",
    },
    {
      n: "05",
      t: "Home hub",
      d: "One app for Rematch official + every Stack-built experience. Discover and launch from one place.",
    },
    {
      n: "06",
      t: "More to come",
      d: "Tournaments, ladders, white-labels, agent matches — shipping weekly. A lot more ahead.",
    },
  ];

  growth.forEach((g, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = MARGIN + col * 4.15;
    const y = 2.85 + row * 1.85;
    s.addText(g.n, {
      x, y, w: 3.9, h: 0.28,
      fontFace: FONT_HEAD, fontSize: 12, bold: true, color: COLOR_ACCENT, charSpacing: 2, margin: 0,
    });
    s.addText(g.t, {
      x, y: y + 0.3, w: 3.9, h: 0.35,
      fontFace: FONT_HEAD, fontSize: 18, bold: true, color: COLOR_TEXT, margin: 0,
    });
    s.addText(g.d, {
      x, y: y + 0.7, w: 3.9, h: 0.95,
      fontFace: FONT_BODY, fontSize: 13, color: COLOR_MUTED_2, margin: 0,
    });
  });

  addFooter(s, "EA FC FOCUS  ·  MORE GAMES  ·  MOBILE SOON  ·  LIVESTREAM AHEAD", 10);
}

// ------------------------------------------------------------
// 11 — Positioning
// ------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: COLOR_BG };
  addTopBar(s, "11 / 13 — POSITION");
  sectionLabel(s, "WHAT WE ARE — AND AREN'T");

  s.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN, y: 1.7, w: 5.95, h: 4.5,
    fill: { color: COLOR_CARD }, line: { color: COLOR_DIV, width: 1 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN, y: 1.7, w: 0.12, h: 4.5,
    fill: { color: COLOR_ACCENT }, line: { color: COLOR_ACCENT, width: 0 },
  });
  s.addText("WE ARE", {
    x: MARGIN + 0.45, y: 2.0, w: 5.2, h: 0.4,
    fontFace: FONT_HEAD, fontSize: 14, bold: true, color: COLOR_ACCENT, charSpacing: 3, margin: 0,
  });
  const are = [
    "Skill settlement for rivals",
    "Social 1v1 with real stakes",
    "Multi-surface: chat → home app",
    "First app on Rematch Stack",
    "Hub for Stack apps long-term",
  ];
  are.forEach((t, i) => {
    s.addText(t, {
      x: MARGIN + 0.45, y: 2.65 + i * 0.55, w: 5.2, h: 0.45,
      fontFace: FONT_BODY, fontSize: 16, color: COLOR_TEXT, margin: 0, valign: "middle",
    });
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN + 6.2, y: 1.7, w: 5.95, h: 4.5,
    fill: { color: COLOR_CARD }, line: { color: COLOR_DIV, width: 1 },
  });
  s.addText("WE AREN'T", {
    x: MARGIN + 6.65, y: 2.0, w: 5.2, h: 0.4,
    fontFace: FONT_HEAD, fontSize: 14, bold: true, color: COLOR_MUTED_2, charSpacing: 3, margin: 0,
  });
  const arent = [
    "A casino or sportsbook",
    "Odds, parlays, or house edge",
    "A generic DeFi yield app",
    "Locked to one chat app forever",
    "\"Trust me\" group-chat banking",
  ];
  arent.forEach((t, i) => {
    s.addText(t, {
      x: MARGIN + 6.65, y: 2.65 + i * 0.55, w: 5.2, h: 0.45,
      fontFace: FONT_BODY, fontSize: 16, color: COLOR_MUTED_2, margin: 0, valign: "middle",
    });
  });

  addFooter(s, "VOICE: SHORT  ·  HUMAN  ·  COMPETITIVE", 11);
}

// ------------------------------------------------------------
// 12 — Roadmap
// ------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: COLOR_BG };
  addTopBar(s, "12 / 13 — ROADMAP");
  sectionLabel(s, "WHERE WE'RE GOING");

  s.addText("Product first. Platform next.", {
    x: MARGIN, y: 1.5, w: 12, h: 0.5,
    fontFace: FONT_HEAD, fontSize: 30, bold: true, color: COLOR_TEXT, margin: 0,
  });

  const phases = [
    {
      phase: "NOW",
      title: "Live Rematch",
      items: [
        "Telegram bot + public channel",
        "USDC escrow + AI proof",
        "EA FC focus · more titles OK",
        "Stack foundation (v0)",
      ],
      hot: true,
    },
    {
      phase: "NEXT",
      title: "Reach & trust",
      items: [
        "Mobile games",
        "WhatsApp + Discord",
        "Livestream + stronger proof",
        "Builder API · mainnet path",
      ],
      hot: false,
    },
    {
      phase: "THEN",
      title: "Open ecosystem",
      items: [
        "Home app: official + Stack apps",
        "Tournaments & white-labels",
        "Agentic skill matches",
        "Season $PLAY · a lot more",
      ],
      hot: false,
    },
  ];

  phases.forEach((p, i) => {
    const x = MARGIN + i * 4.15;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.2, w: 3.95, h: 4.0,
      fill: { color: p.hot ? COLOR_ACCENT : COLOR_CARD },
      line: { color: p.hot ? COLOR_ACCENT : COLOR_DIV, width: 1 },
    });
    s.addText(p.phase, {
      x: x + 0.35, y: 2.45, w: 3.3, h: 0.35,
      fontFace: FONT_HEAD, fontSize: 12, bold: true,
      color: p.hot ? COLOR_BLACK : COLOR_ACCENT, charSpacing: 3, margin: 0,
    });
    s.addText(p.title, {
      x: x + 0.35, y: 2.9, w: 3.3, h: 0.45,
      fontFace: FONT_HEAD, fontSize: 20, bold: true,
      color: p.hot ? COLOR_BLACK : COLOR_TEXT, margin: 0,
    });
    p.items.forEach((item, j) => {
      s.addText(item, {
        x: x + 0.35, y: 3.55 + j * 0.52, w: 3.3, h: 0.48,
        fontFace: FONT_BODY, fontSize: 14,
        color: p.hot ? "0A0A0A" : COLOR_MUTED_2, margin: 0,
      });
    });
  });

  addFooter(s, "ONE MONEY PATH  ·  A LOT MORE TO COME", 12);
}

// ------------------------------------------------------------
// 13 — Close / CTA
// ------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: COLOR_BG };

  s.addText("REMATCH", {
    x: MARGIN, y: 0.4, w: 3, h: 0.4,
    fontFace: FONT_HEAD, fontSize: 13, bold: true,
    color: COLOR_TEXT, charSpacing: 4, margin: 0, wrap: false,
  });
  s.addText("13 / 13 — PLAY", {
    x: SLIDE_W - MARGIN - 3.5, y: 0.4, w: 3.5, h: 0.4,
    fontFace: FONT_HEAD, fontSize: 11, color: COLOR_MUTED_2,
    charSpacing: 2, align: "right", margin: 0,
  });

  s.addImage({
    path: LOGO,
    x: MARGIN, y: 1.1, w: 0.85, h: 0.85,
    altText: "Rematch logo",
  });

  s.addText("Same rivals.\nFair USDC.\nRun it back.", {
    x: MARGIN, y: 2.1, w: 12, h: 1.85,
    fontFace: FONT_HEAD, fontSize: 42, bold: true,
    color: COLOR_TEXT, margin: 0, valign: "top",
  });

  s.addText(
    "Players settle on Rematch. Builders ship on Rematch Stack. Everyone meets in the home app.",
    {
      x: MARGIN, y: 4.15, w: 12, h: 0.4,
      fontFace: FONT_BODY, fontSize: 16, color: COLOR_ACCENT2, margin: 0,
    }
  );

  s.addShape(pres.shapes.LINE, {
    x: MARGIN, y: 4.75, w: SLIDE_W - MARGIN * 2, h: 0,
    line: { color: COLOR_DIV, width: 1 },
  });

  const blocks = [
    { label: "PLAY", value: "t.me/ClawStationOfficialBot" },
    { label: "SITE", value: "playingsidequest.fun/rematch" },
    { label: "BUILDERS", value: "Rematch Stack · home app" },
  ];
  const blockW = (SLIDE_W - MARGIN * 2) / 3;
  blocks.forEach((b, i) => {
    const x = MARGIN + i * blockW;
    s.addText(b.label, {
      x, y: 5.0, w: blockW - 0.2, h: 0.3,
      fontFace: FONT_HEAD, fontSize: 11, color: COLOR_MUTED_2,
      charSpacing: 3, margin: 0,
    });
    s.addText(b.value, {
      x, y: 5.35, w: blockW - 0.2, h: 0.45,
      fontFace: FONT_HEAD, fontSize: 15, bold: true,
      color: i === 0 || i === 2 ? COLOR_ACCENT : COLOR_TEXT, margin: 0,
    });
  });

  s.addText("Lock in. Play. Rematch.  ·  A lot more to come  ·  © sideQuest", {
    x: MARGIN, y: SLIDE_H - 0.55, w: 12, h: 0.3,
    fontFace: FONT_HEAD, fontSize: 12, color: COLOR_MUTED, charSpacing: 1, margin: 0,
  });
}

// ---------- Write ----------
const out = path.join(__dirname, "Rematch_by_sideQuest.pptx");
pres.writeFile({ fileName: out })
  .then((fn) => console.log("Wrote", fn))
  .catch((err) => { console.error(err); process.exit(1); });
