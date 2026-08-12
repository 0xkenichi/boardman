/**
 * Nero reasoning proxy — free LLM layers (server-side keys only).
 *
 * Order (BOARDMAN_NERO_REASONERS, default asi,gemini):
 *   1. ASI:One  (ASI_ONE_API_KEY)
 *   2. Gemini   (GEMINI_API_KEY / GOOGLE_API_KEY)
 * Then client falls back to Stockfish.
 *
 * POST { fen, agent?, legal_moves, legal_san }
 * → { ok, san, uci, source, model } | { ok:false, error, fallback:true }
 */
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ASI_BASE = process.env.ASI_ONE_BASE_URL || "https://api.asi1.ai/v1";
const ASI_MODEL = process.env.ASI_ONE_MODEL || "asi1-mini";
const GEMINI_MODEL = process.env.GEMINI_MODEL || "gemini-2.0-flash";

function asiKey(): string {
  return (process.env.ASI_ONE_API_KEY || process.env.ASI_API_KEY || "").trim();
}
function geminiKey(): string {
  return (
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

function neroPrompt(fen: string, legalUci: string[], legalSan: string[]): { system: string; user: string } {
  const system =
    "You are Nero, a defensive chess grandmaster (Sicilian/French structures). " +
    'Reply with JSON only: {"move":"<one UCI or SAN from the legal list>"}. No other text.';
  const user =
    `FEN: ${fen}\n` +
    `Legal UCI: ${legalUci.slice(0, 60).join(", ")}${legalUci.length > 60 ? "…" : ""}\n` +
    `Legal SAN: ${legalSan.slice(0, 40).join(", ")}\n` +
    "Pick the strongest practical defensive/counterpunching move.";
  return { system, user };
}

async function tryAsi(
  fen: string,
  legalUci: string[],
  legalSan: string[]
): Promise<{ uci: string; san?: string; model: string; source: string } | { error: string }> {
  const key = asiKey();
  if (!key) return { error: "ASI_ONE_API_KEY not set" };
  const { system, user } = neroPrompt(fen, legalUci, legalSan);
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
  if (!parsed.uci) return { error: "ASI non-legal move", };
  return { uci: parsed.uci, san: parsed.san, model: ASI_MODEL, source: "asi1.ai" };
}

async function tryGemini(
  fen: string,
  legalUci: string[],
  legalSan: string[]
): Promise<{ uci: string; san?: string; model: string; source: string } | { error: string }> {
  const key = geminiKey();
  if (!key) return { error: "GEMINI_API_KEY not set" };
  const { system, user } = neroPrompt(fen, legalUci, legalSan);
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

    const errors: string[] = [];
    for (const name of reasonerOrder()) {
      try {
        let result: { uci: string; san?: string; model: string; source: string } | { error: string };
        if (name === "asi" || name === "asi1" || name === "asi-one") {
          result = await tryAsi(fen, legalUci, legalSan);
        } else if (name === "gemini" || name === "google") {
          result = await tryGemini(fen, legalUci, legalSan);
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
          agent,
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
    note: "Nero LLM chain: ASI:One and/or free Gemini; then Stockfish. No Arc gas for thinking.",
  });
}
