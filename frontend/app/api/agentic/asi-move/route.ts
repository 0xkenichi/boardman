/**
 * LLM reasoning proxy for Boardman agents (server-side keys only).
 *
 * Gemini / ASI are a *plus* on each builder's strategy — not a fixed Nero bot.
 * Every builder ships a different mind; pass `strategy` (or we use a demo default
 * for Nero only). Stack still enforces: move must be legal.
 *
 * Order (BOARDMAN_NERO_REASONERS, default asi,gemini):
 *   1. ASI:One  (ASI_ONE_API_KEY)
 *   2. Gemini   (GEMINI_API_KEY / GOOGLE_API_KEY)
 * Then client falls back to Stockfish.
 *
 * POST {
 *   fen, agent?, legal_moves, legal_san?,
 *   strategy?: { agent_name, directive, archetype, blurb, strategy_id,
 *                strategy_notes, principles, avoid, openings, aggression, ... }
 * }
 * → { ok, san, uci, source, model, strategy_id } | { ok:false, error, fallback:true }
 */
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ASI_BASE = process.env.ASI_ONE_BASE_URL || "https://api.asi1.ai/v1";
const ASI_MODEL = process.env.ASI_ONE_MODEL || "asi1-mini";
const GEMINI_MODEL = process.env.GEMINI_MODEL || "gemini-2.0-flash";

type Strategy = {
  agent_name?: string;
  agent_id?: string;
  directive?: string;
  archetype?: string;
  blurb?: string;
  strategy_id?: string;
  strategy_notes?: string;
  principles?: string;
  avoid?: string;
  openings?: string[];
  aggression?: number;
  king_attack?: number;
  counterpunch?: number;
  sacrifice_bias?: number;
  draw_aversion?: number;
};

/** Demo default only when arena omits strategy for Nero — builders should send their own. */
const NERO_DEMO_STRATEGY: Strategy = {
  agent_name: "Nero",
  agent_id: "agent_nero_sicilian_french",
  directive: "WIN. Stay solid, absorb pressure, counterpunch when overextended.",
  archetype: "defender_counter",
  blurb: "Defense-first silo. Sicilian, French, Caro-Kann. Provokes overextension, then converts.",
  strategy_id: "nero_defense_v2",
  strategy_notes:
    "Solid structures; Sicilian/French/Caro ideas; punish overextension; convert endgames carefully. Rarely sac without clear regain.",
  openings: ["sicilian_defence", "french_defence", "caro_kann", "queens_gambit_declined"],
  aggression: 0.85,
  king_attack: 0.9,
  counterpunch: 1.55,
  sacrifice_bias: 0.55,
  draw_aversion: 0.9,
};

function asiKey(): string {
  return (process.env.ASI_ONE_API_KEY || process.env.ASI_API_KEY || "").trim();
}
function geminiKey(): string {
  // Prefer Nero-scoped key if set (e.g. GEMINI_API_KEY_NERO from Vercel)
  return (
    process.env.GEMINI_API_KEY_NERO ||
    process.env.GEMINI_API_KEY ||
    process.env.GOOGLE_API_KEY ||
    process.env.GOOGLE_GENERATIVE_AI_API_KEY ||
    ""
  ).trim();
}

function agentAllowed(agent: string): boolean {
  const raw = (process.env.BOARDMAN_ASI_AGENTS || "nero").toLowerCase();
  if (raw === "*" || raw === "all") return true;
  return raw.split(",").some((t) => agent.toLowerCase().includes(t.trim()));
}

function reasonerOrder(): string[] {
  const raw = (process.env.BOARDMAN_NERO_REASONERS || "asi,gemini").toLowerCase().replace(/\s+/g, "");
  return raw.split(",").filter(Boolean);
}

function normalizeStrategy(raw: unknown, agent: string): Strategy {
  const s = (raw && typeof raw === "object" ? raw : {}) as Strategy;
  const base =
    Object.keys(s).length > 0
      ? s
      : agent.toLowerCase().includes("nero")
        ? { ...NERO_DEMO_STRATEGY }
        : {
            agent_name: agent,
            directive: "WIN. Play the strongest move that fits your strategy.",
            archetype: "balanced",
            strategy_id: "custom",
          };
  return {
    agent_name: String(base.agent_name || agent),
    agent_id: String(base.agent_id || ""),
    directive: String(base.directive || "WIN. Play the strongest move that fits your strategy."),
    archetype: String(base.archetype || "balanced"),
    blurb: String(base.blurb || ""),
    strategy_id: String(base.strategy_id || ""),
    strategy_notes: String(base.strategy_notes || base.principles || ""),
    principles: String(base.principles || ""),
    avoid: String(base.avoid || ""),
    openings: Array.isArray(base.openings) ? base.openings.map(String).slice(0, 24) : [],
    aggression: base.aggression,
    king_attack: base.king_attack,
    counterpunch: base.counterpunch,
    sacrifice_bias: base.sacrifice_bias,
    draw_aversion: base.draw_aversion,
  };
}

/** System prompt from *this builder's* strategy — not a global chess bot. */
function buildSystemPrompt(strategy: Strategy): string {
  const name = strategy.agent_name || "Agent";
  const lines = [
    `You are ${name}, an autonomous chess agent on Boardman Stack.`,
    "You play only legal moves from the provided list.",
    "Your builder defined a unique strategy. Apply it — do not invent a different persona.",
    "",
    `Directive: ${strategy.directive || "WIN."}`,
    `Archetype: ${strategy.archetype || "balanced"}`,
  ];
  if (strategy.blurb) lines.push(`Scout report: ${strategy.blurb}`);
  if (strategy.strategy_id) lines.push(`Strategy id: ${strategy.strategy_id}`);
  if (strategy.strategy_notes || strategy.principles) {
    lines.push(`Strategy notes: ${strategy.strategy_notes || strategy.principles}`);
  }
  if (strategy.avoid) lines.push(`Avoid: ${strategy.avoid}`);
  if (strategy.openings?.length) {
    lines.push("Preferred openings / ideas: " + strategy.openings.join(", "));
  }
  const knobs: string[] = [];
  for (const [label, key] of [
    ["aggression", "aggression"],
    ["king attack", "king_attack"],
    ["counterpunch", "counterpunch"],
    ["sacrifice bias", "sacrifice_bias"],
    ["draw aversion", "draw_aversion"],
  ] as const) {
    const v = strategy[key];
    if (v != null && Number.isFinite(Number(v))) knobs.push(`${label}=${Number(v).toFixed(2)}`);
  }
  if (knobs.length) lines.push("Style knobs (1.0 = neutral): " + knobs.join(", "));
  lines.push(
    "",
    "When choosing a move:",
    "1) Prefer lines that fit the strategy notes over generic engine chess.",
    "2) Still refuse blunders that clearly hang heavy material when avoidable.",
    '3) Reply with JSON only: {"move":"<UCI or SAN from the legal list>"}.',
    "No commentary outside JSON."
  );
  return lines.join("\n");
}

function buildUserPrompt(fen: string, legalUci: string[], legalSan: string[]): string {
  return (
    `FEN: ${fen}\n` +
    `Legal UCI: ${legalUci.slice(0, 60).join(", ")}${legalUci.length > 60 ? "…" : ""}\n` +
    `Legal SAN: ${legalSan.slice(0, 40).join(", ")}\n` +
    "Pick one legal move that best executes YOUR strategy."
  );
}

function parseMove(text: string, legalUci: string[], legalSan: string[]): { uci?: string; san?: string } {
  if (!text) return {};
  try {
    const m = text.match(/\{[^{}]+\}/);
    if (m) {
      const obj = JSON.parse(m[0]) as { move?: string; uci?: string; san?: string };
      const cand = String(obj.move || obj.uci || obj.san || "").trim();
      const hit = matchLegal(cand, legalUci, legalSan);
      if (hit) return hit;
    }
  } catch {
    /* continue */
  }
  const uciRe = /\b([a-h][1-8][a-h][1-8][qrbn]?)\b/gi;
  let mm: RegExpExecArray | null;
  while ((mm = uciRe.exec(text))) {
    const hit = matchLegal(mm[1], legalUci, legalSan);
    if (hit) return hit;
  }
  for (const tok of text.replace(/[`"'.,]/g, " ").split(/\s+/).sort((a, b) => b.length - a.length)) {
    if (tok.length < 2) continue;
    const hit = matchLegal(tok, legalUci, legalSan);
    if (hit) return hit;
  }
  return {};
}

function matchLegal(cand: string, legalUci: string[], legalSan: string[]): { uci?: string; san?: string } | null {
  const c = cand.trim();
  const cl = c.toLowerCase();
  const ui = legalUci.findIndex((u) => u.toLowerCase() === cl);
  if (ui >= 0) return { uci: legalUci[ui], san: legalSan[ui] };
  const si = legalSan.findIndex((s) => s === c || s.replace(/[+#]/g, "") === c.replace(/[+#]/g, ""));
  if (si >= 0) return { uci: legalUci[si], san: legalSan[si] };
  return null;
}

async function tryAsi(
  system: string,
  user: string,
  legalUci: string[],
  legalSan: string[]
): Promise<{ uci: string; san?: string; model: string; source: string } | { error: string }> {
  const key = asiKey();
  if (!key) return { error: "ASI_ONE_API_KEY not set" };
  const r = await fetch(`${ASI_BASE.replace(/\/$/, "")}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${key}`,
    },
    body: JSON.stringify({
      model: ASI_MODEL,
      messages: [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
      temperature: 0.15,
      max_tokens: 128,
    }),
    signal: AbortSignal.timeout(25000),
  });
  if (!r.ok) {
    const errText = await r.text().catch(() => "");
    return { error: `ASI HTTP ${r.status}: ${errText.slice(0, 160)}` };
  }
  const data = (await r.json()) as {
    choices?: Array<{ message?: { content?: string | Array<{ text?: string }> } }>;
  };
  let content = data.choices?.[0]?.message?.content || "";
  if (Array.isArray(content)) {
    content = content.map((p) => (typeof p === "string" ? p : p?.text || "")).join(" ");
  }
  const parsed = parseMove(String(content), legalUci, legalSan);
  if (!parsed.uci) return { error: "ASI non-legal move" };
  return { uci: parsed.uci, san: parsed.san, model: ASI_MODEL, source: "asi1.ai" };
}

async function tryGemini(
  system: string,
  user: string,
  legalUci: string[],
  legalSan: string[]
): Promise<{ uci: string; san?: string; model: string; source: string } | { error: string }> {
  const key = geminiKey();
  if (!key) return { error: "GEMINI_API_KEY_NERO / GEMINI_API_KEY not set" };
  const url =
    `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(GEMINI_MODEL)}:generateContent` +
    `?key=${encodeURIComponent(key)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [
        {
          role: "user",
          parts: [{ text: system + "\n\n" + user }],
        },
      ],
      generationConfig: { temperature: 0.15, maxOutputTokens: 128 },
    }),
    signal: AbortSignal.timeout(25000),
  });
  if (!r.ok) {
    const errText = await r.text().catch(() => "");
    return { error: `Gemini HTTP ${r.status}: ${errText.slice(0, 160)}` };
  }
  const data = (await r.json()) as {
    candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
  };
  const parts = data.candidates?.[0]?.content?.parts || [];
  const content = parts.map((p) => p.text || "").join("\n");
  const parsed = parseMove(content, legalUci, legalSan);
  if (!parsed.uci) return { error: "Gemini non-legal move" };
  return { uci: parsed.uci, san: parsed.san, model: GEMINI_MODEL, source: "gemini" };
}

export async function POST(req: NextRequest) {
  try {
    const body = (await req.json().catch(() => ({}))) as {
      fen?: string;
      agent?: string;
      legal_moves?: string[];
      legal_san?: string[];
      strategy?: Strategy;
      mind?: Strategy;
    };
    const agent = String(body.agent || "nero");
    if (!agentAllowed(agent)) {
      return NextResponse.json(
        { ok: false, error: "agent not configured for LLM reasoning", fallback: true },
        { status: 200 }
      );
    }
    const fen = String(body.fen || "");
    if (!fen) {
      return NextResponse.json({ ok: false, error: "fen required", fallback: true }, { status: 400 });
    }
    const legalUci = Array.isArray(body.legal_moves) ? body.legal_moves.map(String) : [];
    const legalSan = Array.isArray(body.legal_san) ? body.legal_san.map(String) : [];
    if (!legalUci.length) {
      return NextResponse.json(
        { ok: false, error: "legal_moves required (client chess.js)", fallback: true },
        { status: 200 }
      );
    }

    const strategy = normalizeStrategy(body.strategy || body.mind, agent);
    const system = buildSystemPrompt(strategy);
    const user = buildUserPrompt(fen, legalUci, legalSan);

    const errors: string[] = [];
    for (const name of reasonerOrder()) {
      try {
        let result: { uci: string; san?: string; model: string; source: string } | { error: string };
        if (name === "asi" || name === "asi1" || name === "asi-one") {
          result = await tryAsi(system, user, legalUci, legalSan);
        } else if (name === "gemini" || name === "google") {
          result = await tryGemini(system, user, legalUci, legalSan);
        } else {
          continue;
        }
        if ("error" in result) {
          errors.push(`${name}: ${result.error}`);
          continue;
        }
        return NextResponse.json({
          ok: true,
          uci: result.uci,
          san: result.san,
          source: result.source,
          model: result.model,
          agent: strategy.agent_name || agent,
          strategy_id: strategy.strategy_id || "",
        });
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        errors.push(`${name}: ${msg}`);
      }
    }

    return NextResponse.json({
      ok: false,
      error: errors.length ? errors.join(" | ") : "no LLM reasoners configured",
      fallback: true,
      tried: reasonerOrder(),
      asi_configured: Boolean(asiKey()),
      gemini_configured: Boolean(geminiKey()),
      strategy_id: strategy.strategy_id || "",
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ ok: false, error: msg, fallback: true }, { status: 200 });
  }
}

export async function GET() {
  return NextResponse.json({
    ok: true,
    asi_configured: Boolean(asiKey()),
    gemini_configured: Boolean(geminiKey()),
    asi_model: ASI_MODEL,
    gemini_model: GEMINI_MODEL,
    order: reasonerOrder(),
    agents: process.env.BOARDMAN_ASI_AGENTS || "nero",
    note:
      "LLM keys amplify each builder's strategy (pass strategy JSON). " +
      "Not a one-size Nero bot. Stockfish remains free fallback. No Arc gas for thinking.",
  });
}
