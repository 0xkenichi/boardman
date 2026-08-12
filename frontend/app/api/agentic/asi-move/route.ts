/**
 * Free ASI:One reasoning proxy for Nero (server-side key only).
 *
 * POST { fen, agent?: "nero" }
 * → { ok, san, uci, source, model } | { ok:false, error, fallback:true }
 *
 * Env: ASI_ONE_API_KEY (or ASI_API_KEY), optional ASI_ONE_MODEL=asi1-mini
 */
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BASE = process.env.ASI_ONE_BASE_URL || "https://api.asi1.ai/v1";
const MODEL = process.env.ASI_ONE_MODEL || "asi1-mini";

function apiKey(): string {
  return (process.env.ASI_ONE_API_KEY || process.env.ASI_API_KEY || "").trim();
}

function agentAllowed(agent: string): boolean {
  const raw = (process.env.BOARDMAN_ASI_AGENTS || "nero").toLowerCase();
  if (raw === "*" || raw === "all") return true;
  return raw.split(",").some((t) => agent.toLowerCase().includes(t.trim()));
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
      return NextResponse.json({ ok: false, error: "agent not configured for ASI", fallback: true }, { status: 200 });
    }
    const key = apiKey();
    if (!key) {
      return NextResponse.json(
        { ok: false, error: "ASI_ONE_API_KEY not set on server (free key from asi1.ai)", fallback: true },
        { status: 200 }
      );
    }
    const fen = String(body.fen || "");
    if (!fen) {
      return NextResponse.json({ ok: false, error: "fen required", fallback: true }, { status: 400 });
    }

    // Arena always sends legal_moves from chess.js client — no server chess dep
    const legalUci = Array.isArray(body.legal_moves) ? body.legal_moves.map(String) : [];
    const legalSan = Array.isArray(body.legal_san) ? body.legal_san.map(String) : [];
    if (!legalUci.length) {
      return NextResponse.json(
        { ok: false, error: "legal_moves required (client chess.js)", fallback: true },
        { status: 200 }
      );
    }

    const system =
      "You are Nero, a defensive chess grandmaster (Sicilian/French structures). " +
      'Reply with JSON only: {"move":"<one UCI or SAN from the legal list>"}. No other text.';
    const user =
      `FEN: ${fen}\n` +
      `Legal UCI: ${legalUci.slice(0, 60).join(", ")}${legalUci.length > 60 ? "…" : ""}\n` +
      `Legal SAN: ${legalSan.slice(0, 40).join(", ")}\n` +
      "Pick the strongest practical defensive/counterpunching move.";

    const r = await fetch(`${BASE.replace(/\/$/, "")}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${key}`,
      },
      body: JSON.stringify({
        model: MODEL,
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
      return NextResponse.json(
        { ok: false, error: `ASI HTTP ${r.status}: ${errText.slice(0, 200)}`, fallback: true },
        { status: 200 }
      );
    }
    const data = (await r.json()) as {
      choices?: Array<{ message?: { content?: string | Array<{ text?: string }> } }>;
    };
    let content = data.choices?.[0]?.message?.content || "";
    if (Array.isArray(content)) {
      content = content.map((p) => (typeof p === "string" ? p : p?.text || "")).join(" ");
    }
    const parsed = parseMove(String(content), legalUci, legalSan);
    if (!parsed.uci) {
      return NextResponse.json(
        { ok: false, error: "ASI returned non-legal move", raw: String(content).slice(0, 300), fallback: true },
        { status: 200 }
      );
    }
    return NextResponse.json({
      ok: true,
      uci: parsed.uci,
      san: parsed.san,
      source: "asi1.ai",
      model: MODEL,
      agent,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ ok: false, error: msg, fallback: true }, { status: 200 });
  }
}

export async function GET() {
  return NextResponse.json({
    ok: true,
    asi_configured: Boolean(apiKey()),
    model: MODEL,
    agents: process.env.BOARDMAN_ASI_AGENTS || "nero",
    note: "POST { fen, agent:'nero' } — free ASI:One key; Arc not required for thinking",
  });
}
