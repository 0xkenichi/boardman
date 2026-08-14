/**
 * Arena Auto play / Play match → Boardman House rematch
 * (open → lock stakes → builder webhooks play → settle).
 */
import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { rematchApiFetch, rematchApiConfigured } from "@/lib/stackServer";
import { clientIp, rateLimit } from "@/lib/rateLimit";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function localStackBase(): string {
  return (
    process.env.BOARDMAN_API_URL ||
    process.env.REMATCH_API_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
}

async function stackCall(pathName: string, init: RequestInit = {}) {
  if (rematchApiConfigured()) {
    return rematchApiFetch(pathName, init);
  }
  const key =
    process.env.BOARDMAN_API_KEY ||
    process.env.REMATCH_API_KEY ||
    process.env.STACK_API_KEY ||
    "";
  const url = `${localStackBase()}${pathName}`;
  const headers = new Headers(init.headers || {});
  if (key) {
    headers.set("X-Rematch-Key", key);
    headers.set("X-Stack-Key", key);
  }
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  try {
    const res = await fetch(url, { ...init, headers, cache: "no-store" });
    const text = await res.text();
    let data: any = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { raw: text };
    }
    return { ok: res.ok, status: res.status, data };
  } catch (e: any) {
    return {
      ok: false,
      status: 502,
      data: {
        error: "House API is offline. Play match needs the Boardman API running (not just Vercel).",
        detail: String(e?.message || e),
      },
    };
  }
}

function findMatchLocal(id: string): any | null {
  const env = process.env.BOARDMAN_AGENTIC_DATA;
  const candidates = [
    env ? path.join(env, "matches.json") : "",
    path.resolve(process.cwd(), "data/agentic/matches.json"),
    path.resolve(process.cwd(), "../data/agentic/matches.json"),
    path.resolve(process.cwd(), "../../data/agentic/matches.json"),
  ].filter(Boolean);
  for (const p of candidates) {
    try {
      if (!fs.existsSync(p)) continue;
      const store = JSON.parse(fs.readFileSync(p, "utf8"));
      const rec = store?.matches?.[id];
      if (rec) return rec;
    } catch {
      /* next */
    }
  }
  return null;
}

export async function POST(req: NextRequest) {
  const rl = rateLimit(`house-play:${clientIp(req)}`, { limit: 8, windowMs: 60_000 });
  if (!rl.ok) {
    return NextResponse.json(
      { ok: false, error: "rate_limited", retry_after: rl.retryAfterSec },
      { status: 429 }
    );
  }
  let body: any = {};
  try {
    body = await req.json();
  } catch {
    body = {};
  }
  const r = await stackCall("/api/stack/agentic/house/rematch", {
    method: "POST",
    body: JSON.stringify({
      stake_usdc: Number(body.stake_usdc) > 0 ? Number(body.stake_usdc) : 1,
      white: body.white === "nero" ? "nero" : "raja",
      wait: false,
      move_delay_sec: 0.05,
      game_id: "agentic.chess_standard",
    }),
  });
  if (!r.ok) {
    return NextResponse.json(
      {
        ok: false,
        error:
          r.data?.detail ||
          r.data?.error ||
          "House API is offline. Play match needs the Boardman API running.",
        status: r.status,
      },
      { status: r.status || 502 }
    );
  }
  const match = r.data?.match || {};
  return NextResponse.json({
    ok: true,
    match_id: r.data?.match_id || match.match_id,
    status: r.data?.status || match.status || "locking",
    match,
    clerk: "agent_boardman_house",
  });
}

export async function GET(req: NextRequest) {
  const id = req.nextUrl.searchParams.get("id") || "";
  if (!id) {
    return NextResponse.json({ ok: false, error: "missing id" }, { status: 400 });
  }
  const r = await stackCall(`/api/stack/agentic/matches/${encodeURIComponent(id)}`);
  if (r.ok && r.data?.match) {
    return NextResponse.json({ ok: true, match: r.data.match });
  }
  const local = findMatchLocal(id);
  if (local) {
    return NextResponse.json({ ok: true, match: local, source: "local_file" });
  }
  return NextResponse.json(
    { ok: false, error: r.data?.detail || "match not found" },
    { status: r.status || 404 }
  );
}
