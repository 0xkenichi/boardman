/**
 * LLM reasoning proxy for Boardman agents (server-side keys only).
 *
 * Per-agent keys (do not share one brain credential across agents):
 *   GEMINI_API_KEY_NERO / GEMINI_API_KEY_RAJA / GEMINI_API_KEY_<SLUG>
 *   ASI_ONE_API_KEY_NERO / ASI_ONE_API_KEY_RAJA / ASI_ONE_API_KEY_<SLUG>
 * Shared fallback only if agent is on BOARDMAN_LLM_AGENTS allow-list:
 *   GEMINI_API_KEY / ASI_ONE_API_KEY
 *
 * Every agent is bound to wallet_address for stakes; chess legality is FIDE.
 * Rule book is injected into the system prompt; only legal_moves may be returned.
 *
 * POST {
 *   fen, agent?, agent_id?, wallet?, legal_moves, legal_san?,
 *   strategy?: { ... mind / strategy fields, wallet_address }
 * }
 */
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ASI_BASE = process.env.ASI_ONE_BASE_URL || "https://api.asi1.ai/v1";
const ASI_MODEL = process.env.ASI_ONE_MODEL || "asi1-mini";
const GEMINI_MODEL = process.env.GEMINI_MODEL || "gemini-2.0-flash";

const RULE_BOOK_COMPACT = `
=== BOARDMAN CHESS RULE BOOK (MANDATORY — NEVER BREAK) ===
Source: FIDE Laws of Chess (Articles 1–5). You are bound by these rules.

1. BOARD & SETUP — 8×8, White moves first, alternate turns, one legal move.
2. PIECES — K:1 sq; Q: rank/file/diag; R: rank/file; B: diag; N: L-jump; P: fwd 1/2, capture diag.
3. CHECK — must resolve (move king / capture / block). NEVER leave own king in check.
4. CHECKMATE — king in check with no legal escape → lose. Game over.
5. CASTLING — king 2 toward rook, rook to crossed square; only if neither moved, path clear, not through/into/out of check.
6. EN PASSANT — only on the move immediately after opponent double-pawn push.
7. PROMOTION — pawn on last rank must become Q/R/B/N same move.
8. ILLEGAL — anything not in the provided legal_moves list is FORBIDDEN.
9. DRAWS — stalemate, dead position, repetition, 50/75-move as applicable.
10. Strategy never overrides legality. Reply JSON only: {"move":"<UCI or SAN from list>"}.
=== END RULE BOOK ===
`.trim();

type Strategy = {
  agent_name?: string;
  agent_id?: string;
  wallet_address?: string;
  wallet?: string;
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

const RAJA_DEMO_STRATEGY: Strategy = {
  agent_name: "Raja",
  agent_id: "agent_raja_kia_alekhine",
  directive: "WIN by attack. Attack is the best defence. Hunt the king, force mates.",
  archetype: "attacker",
  blurb: "Mate-hungry attacker. KIA storms, Open Sicilian Yugoslav, Italian pressure.",
  strategy_id: "raja_mate_hunter_v3",
  strategy_notes: "Initiative first; king hunts; refuse quiet equality when an attack exists.",
  openings: ["kings_indian_attack", "yugoslav_attack", "italian_fried_liver", "alekhines_defence"],
  aggression: 1.85,
  king_attack: 1.9,
  counterpunch: 0.55,
  sacrifice_bias: 1.55,
  draw_aversion: 1.7,
};

function agentSlugs(agent: string, agentId: string): string[] {
  const hay = `${agent} ${agentId}`.toLowerCase();
  const out: string[] = [];
  const push = (s: string) => {
    const t = s.replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
    if (t && !out.includes(t)) out.push(t);
  };
  if (agent) push(agent);
  if (agentId) {
    push(agentId);
    for (const p of agentId.replace(/-/g, "_").split("_")) {
      if (p && !["agent", "v1", "v2", "v3"].includes(p)) push(p);
    }
  }
  if (hay.includes("nero")) push("nero");
  if (hay.includes("raja")) push("raja");
  return out;
}

function allowList(): string[] {
  const raw = (process.env.BOARDMAN_LLM_AGENTS || process.env.BOARDMAN_ASI_AGENTS || "nero,raja").toLowerCase();
  if (raw === "*" || raw === "all") return ["*"];
  return raw.split(",").map((t) => t.trim()).filter(Boolean);
}

function onAllowList(agent: string, agentId: string): boolean {
  const tokens = allowList();
  if (tokens.includes("*")) return true;
  const hay = `${agent} ${agentId}`.toLowerCase();
  return tokens.some((t) => hay.includes(t));
}

function resolveGeminiKey(agent: string, agentId: string): string {
  const slugs = agentSlugs(agent, agentId);
  for (const s of slugs) {
    const k = (process.env[`GEMINI_API_KEY_${s.toUpperCase()}`] || "").trim();
    if (k) return k;
  }
  const shared = (
    process.env.GEMINI_API_KEY ||
    process.env.GOOGLE_API_KEY ||
    process.env.GOOGLE_GENERATIVE_AI_API_KEY ||
    ""
  ).trim();
  if (shared && onAllowList(agent, agentId)) return shared;
  // historical Nero-scoped shared
  const nero = (process.env.GEMINI_API_KEY_NERO || "").trim();
  if (nero && `${agent} ${agentId}`.toLowerCase().includes("nero")) return nero;
  return "";
}

function resolveAsiKey(agent: string, agentId: string): string {
  const slugs = agentSlugs(agent, agentId);
  for (const s of slugs) {
    const k = (
      process.env[`ASI_ONE_API_KEY_${s.toUpperCase()}`] ||
      process.env[`ASI_API_KEY_${s.toUpperCase()}`] ||
      ""
    ).trim();
    if (k) return k;
  }
  const shared = (process.env.ASI_ONE_API_KEY || process.env.ASI_API_KEY || "").trim();
  if (shared && onAllowList(agent, agentId)) return shared;
  return "";
}

function reasonerOrder(): string[] {
  const raw = (process.env.BOARDMAN_LLM_REASONERS || process.env.BOARDMAN_NERO_REASONERS || "asi,gemini")
    .toLowerCase()
    .replace(/\s+/g, "");
  return raw.split(",").filter(Boolean);
}

function normalizeStrategy(raw: unknown, agent: string, agentId: string, wallet: string): Strategy {
  const s = (raw && typeof raw === "object" ? raw : {}) as Strategy;
  let base: Strategy;
  if (Object.keys(s).length > 0) {
    base = s;
  } else if (agent.toLowerCase().includes("nero") || agentId.toLowerCase().includes("nero")) {
    base = { ...NERO_DEMO_STRATEGY };
  } else if (agent.toLowerCase().includes("raja") || agentId.toLowerCase().includes("raja")) {
    base = { ...RAJA_DEMO_STRATEGY };
  } else {
    base = {
      agent_name: agent,
      directive: "WIN. Play the strongest move that fits your strategy.",
      archetype: "balanced",
      strategy_id: "custom",
    };
  }
  return {
    agent_name: String(base.agent_name || agent),
    agent_id: String(base.agent_id || agentId || ""),
    wallet_address: String(base.wallet_address || base.wallet || wallet || ""),
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

function buildSystemPrompt(strategy: Strategy): string {
  const name = strategy.agent_name || "Agent";
  const lines = [
    `You are ${name}, an autonomous chess agent on Boardman Stack.`,
    "You play only legal moves from the provided list.",
    "Your builder defined a unique strategy. Apply it — do not invent a different persona.",
    "You MUST NEVER break the Boardman Chess Rule Book (FIDE Laws). Legality overrides style.",
    "",
    `Directive: ${strategy.directive || "WIN."}`,
    `Archetype: ${strategy.archetype || "balanced"}`,
  ];
  if (strategy.wallet_address) lines.push(`Wallet identity (stakes / settlement): ${strategy.wallet_address}`);
  if (strategy.agent_id) lines.push(`Agent id: ${strategy.agent_id}`);
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
    "3) Never leave your king in check; never break castling / en passant / promotion rules.",
    '4) Reply with JSON only: {"move":"<UCI or SAN from the legal list>"}.',
    "No commentary outside JSON.",
    "",
    RULE_BOOK_COMPACT
  );
  return lines.join("\n");
}

function buildUserPrompt(fen: string, legalUci: string[], legalSan: string[]): string {
  return (
    `FEN: ${fen}\n` +
    `Legal UCI: ${legalUci.slice(0, 60).join(", ")}${legalUci.length > 60 ? "…" : ""}\n` +
    `Legal SAN: ${legalSan.slice(0, 40).join(", ")}\n` +
    "Pick one legal move that best executes YOUR strategy. Never break the rule book."
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
  legalSan: string[],
  apiKey: string
): Promise<{ uci: string; san?: string; model: string; source: string } | { error: string }> {
  if (!apiKey) return { error: "ASI key not set for this agent" };
  console.info("[asi-move] calling ASI model=%s", ASI_MODEL);
  const r = await fetch(`${ASI_BASE.replace(/\/$/, "")}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
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
    console.warn("[asi-move] ASI HTTP %s %s", r.status, errText.slice(0, 120));
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
  if (!parsed.uci) return { error: "ASI non-legal move (rule book reject)" };
  console.info("[asi-move] ASI ok uci=%s", parsed.uci);
  return { uci: parsed.uci, san: parsed.san, model: ASI_MODEL, source: "asi1.ai" };
}

async function tryGemini(
  system: string,
  user: string,
  legalUci: string[],
  legalSan: string[],
  apiKey: string
): Promise<{ uci: string; san?: string; model: string; source: string } | { error: string }> {
  if (!apiKey) return { error: "Gemini key not set for this agent" };
  console.info("[asi-move] calling Gemini model=%s", GEMINI_MODEL);
  const url =
    `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(GEMINI_MODEL)}:generateContent` +
    `?key=${encodeURIComponent(apiKey)}`;
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
    console.warn("[asi-move] Gemini HTTP %s %s", r.status, errText.slice(0, 120));
    return { error: `Gemini HTTP ${r.status}: ${errText.slice(0, 160)}` };
  }
  const data = (await r.json()) as {
    candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
  };
  const parts = data.candidates?.[0]?.content?.parts || [];
  const content = parts.map((p) => p.text || "").join("\n");
  const parsed = parseMove(content, legalUci, legalSan);
  if (!parsed.uci) return { error: "Gemini non-legal move (rule book reject)" };
  console.info("[asi-move] Gemini ok uci=%s", parsed.uci);
  return { uci: parsed.uci, san: parsed.san, model: GEMINI_MODEL, source: "gemini" };
}

export async function POST(req: NextRequest) {
  try {
    const body = (await req.json().catch(() => ({}))) as {
      fen?: string;
      agent?: string;
      agent_id?: string;
      wallet?: string;
      wallet_address?: string;
      legal_moves?: string[];
      legal_san?: string[];
      strategy?: Strategy;
      mind?: Strategy;
    };
    const agent = String(body.agent || body.strategy?.agent_name || "nero");
    const agentId = String(body.agent_id || body.strategy?.agent_id || "");
    const wallet = String(body.wallet_address || body.wallet || body.strategy?.wallet_address || "");

    const geminiKey = resolveGeminiKey(agent, agentId);
    const asiKey = resolveAsiKey(agent, agentId);
    if (!geminiKey && !asiKey) {
      return NextResponse.json(
        {
          ok: false,
          error: `no LLM API key for agent '${agent}' (set GEMINI_API_KEY_${agent.toUpperCase()} or ASI_ONE_API_KEY_${agent.toUpperCase()})`,
          fallback: true,
          gemini_configured: false,
          asi_configured: false,
          agent,
          agent_id: agentId,
          wallet_address: wallet,
        },
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

    const strategy = normalizeStrategy(body.strategy || body.mind, agent, agentId, wallet);
    const system = buildSystemPrompt(strategy);
    const user = buildUserPrompt(fen, legalUci, legalSan);

    const errors: string[] = [];
    const tried: string[] = [];
    for (const name of reasonerOrder()) {
      try {
        let result: { uci: string; san?: string; model: string; source: string } | { error: string };
        if (name === "asi" || name === "asi1" || name === "asi-one") {
          tried.push("asi");
          result = await tryAsi(system, user, legalUci, legalSan, asiKey);
        } else if (name === "gemini" || name === "google") {
          tried.push("gemini");
          result = await tryGemini(system, user, legalUci, legalSan, geminiKey);
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
          agent_id: strategy.agent_id || agentId,
          wallet_address: strategy.wallet_address || wallet,
          strategy_id: strategy.strategy_id || "",
          rule_book: "fide-2023-boardman-v1",
          api_call: result.source,
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
      tried,
      asi_configured: Boolean(asiKey),
      gemini_configured: Boolean(geminiKey),
      strategy_id: strategy.strategy_id || "",
      agent,
      agent_id: agentId,
      wallet_address: wallet,
      rule_book: "fide-2023-boardman-v1",
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ ok: false, error: msg, fallback: true }, { status: 200 });
  }
}

export async function GET() {
  const demo = [
    { agent: "nero", agent_id: "agent_nero_sicilian_french" },
    { agent: "raja", agent_id: "agent_raja_kia_alekhine" },
  ];
  return NextResponse.json({
    ok: true,
    rule_book: {
      version: "fide-2023-boardman-v1",
      authority: "FIDE Laws of Chess (2023)",
      binding: "all Boardman chess agents — never break",
      doc: "/agentic/docs.html#chess-rule-book",
    },
    order: reasonerOrder(),
    agents_allow: allowList(),
    per_agent: demo.map((d) => ({
      ...d,
      gemini_configured: Boolean(resolveGeminiKey(d.agent, d.agent_id)),
      asi_configured: Boolean(resolveAsiKey(d.agent, d.agent_id)),
      gemini_dedicated: Boolean(
        process.env[`GEMINI_API_KEY_${d.agent.toUpperCase()}`]
      ),
      asi_dedicated: Boolean(
        process.env[`ASI_ONE_API_KEY_${d.agent.toUpperCase()}`]
      ),
    })),
    asi_model: ASI_MODEL,
    gemini_model: GEMINI_MODEL,
    note:
      "Set GEMINI_API_KEY_NERO and GEMINI_API_KEY_RAJA (and/or ASI_ONE_API_KEY_*) " +
      "so each agent has its own teaching key. Shared keys only apply to BOARDMAN_LLM_AGENTS. " +
      "Illegal moves are rejected. Stockfish remains free fallback.",
  });
}
