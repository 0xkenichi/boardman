/**
 * Arena Auto play / Play match → Boardman House rematch
 * (open → lock stakes → builder webhooks play → settle).
 */
import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";
// stackCall: configured API or local :8000, 8s timeout, fast 502/504 when offline
import { stackCall } from "@/lib/stackServer";
import { clientIp, rateLimit } from "@/lib/rateLimit";
import { requireAdmin } from "@/lib/adminAuth";
import { requireSession } from "@/lib/bff";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

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
  const auth = requireAdmin(req);
  if ("error" in auth) return auth.error;
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
  const rematchBody: Record<string, unknown> = {
    white: body.white === "nero" || body.white === "sheila" ? body.white : "raja",
    wait: false,
    move_delay_sec: 0.05,
    game_id: "agentic.chess_standard",
  };
  const stake = Number(body.stake_usdc);
  if (Number.isFinite(stake) && stake > 0) rematchBody.stake_usdc = stake;
  const r = await stackCall("/api/stack/agentic/house/rematch", {
    method: "POST",
    body: JSON.stringify(rematchBody),
  });
  if (!r.ok) {
    const detail = String(r.data?.detail || r.data?.error || "");
    const live = detail.match(/already live on (agm_[a-z0-9]+)/i);
    if (live) {
      const got = await stackCall(
        `/api/stack/agentic/matches/${encodeURIComponent(live[1])}`
      );
      const attached = got.data?.match;
      if (got.ok && attached?.match_id) {
        return NextResponse.json({
          ok: true,
          match_id: attached.match_id,
          status: attached.status || "playing",
          match: attached,
          attached: true,
          clerk: "agent_boardman_house",
        });
      }
    }
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
  // Ticket-outcome probe: the arena's ticket checker asks specifically about
  // one table so a bettor's resolved ticket never depends on what the floor
  // is seating now.
  const statusFor = req.nextUrl.searchParams.get("status_for") || "";
  if (statusFor) {
    // Ticket-outcome probe: the arena's ticket checker asks about ONE table
    // so a bettor's resolved ticket never depends on what the floor seats now.
    // Outcome AND payout come straight from the settled spectator book.
    if (!/^agm_[a-z0-9]+$/i.test(statusFor)) {
      return NextResponse.json({ ok: false, error: "bad_match_id" }, { status: 400 });
    }
    // Which bettor is asking? (Telegram session on this browser.)
    let bettorId = "";
    try {
      const auth = requireSession(req);
      if (!("error" in auth)) bettorId = String(auth.session.profileId || "");
    } catch {}
    if (!bettorId) {
      // Not signed in — the ticket on this browser can't be attributed.
      return NextResponse.json(
        { ok: true, settled: false, reason: "not_signed_in" },
        { headers: { "Cache-Control": "no-store" } }
      );
    }
    const book = await stackCall(
      `/api/stack/agentic/matches/${encodeURIComponent(statusFor)}/spectator`
    );
    if (!book.ok) {
      return NextResponse.json(
        { ok: false, error: "book_unavailable" },
        { status: 502, headers: { "Cache-Control": "no-store" } }
      );
    }
    const bookData = book.data?.book || {};
    if (String(bookData.status || "") !== "settled") {
      return NextResponse.json(
        { ok: true, settled: false, status: bookData.status || "" },
        { headers: { "Cache-Control": "no-store" } }
      );
    }
    const bets = Array.isArray(bookData.bets) ? bookData.bets : [];
    const mine = bets.find(
      (b: any) => String(b.bettor_id || "") === bettorId
    );
    if (!mine) {
      return NextResponse.json(
        { ok: true, settled: false, reason: "no_ticket_on_this_table" },
        { headers: { "Cache-Control": "no-store" } }
      );
    }
    const end = bookData.payouts || {};
    let outcome: "win" | "loss" | "refund" = "loss";
    let payout: number | undefined;
    if (end.mode === "draw_hits" || end.mode === "draw_seed_return") {
      outcome = "refund";
      payout = Number(end.payout) || undefined;
    }
    const winnerSide = end.winner_side || null;
    if (winnerSide && String(mine.side || "") === winnerSide) {
      const mine_pay = (end.bettors || []).find(
        (p: any) => String(p.bettor_id || "") === bettorId
      );
      outcome = "win";
      payout = Number(mine_pay?.amount) || undefined;
    }
    return NextResponse.json(
      {
        ok: true,
        settled: true,
        outcome,
        payout,
        ended_at: bookData.settled_at,
      },
      { headers: { "Cache-Control": "no-store" } }
    );
  }
  if (!id) {
    const floor = await stackCall("/api/stack/agentic/house/floor");
    if (!floor.ok) {
      // Transient backend/tunnel failure — tell the client to KEEP its last
      // board instead of treating this as "no live game".
      return NextResponse.json(
        { ok: false, error: "house_api_unreachable" },
        { status: 502, headers: { "Cache-Control": "no-store" } }
      );
    }
    const tables = floor.data?.floor?.tables || floor.data?.tables || [];
    // Any two house chess contestants (Raja, Nero, Sheila, future agents) —
    // not just the founding pair.
    const isHouseChess = (t: any) => {
      const a = String(t?.agent_a_id || "");
      const b = String(t?.agent_b_id || "");
      return (
        a.startsWith("agent_") &&
        !a.startsWith("agent_floor") &&
        b.startsWith("agent_") &&
        !b.startsWith("agent_floor") &&
        a !== b
      );
    };
    const live = tables.find(
      (t: any) =>
        isHouseChess(t) &&
        ["playing", "locking", "locked", "open"].includes(String(t?.status || ""))
    );
    if (!live?.match_id) {
      const recent = await stackCall("/api/stack/agentic/matches?limit=20");
      const list = recent.data?.matches || recent.data?.items || [];
      const last = (Array.isArray(list) ? list : []).find(
        (t: any) => isHouseChess(t) && String(t?.status || "") === "settled"
      );
      if (last?.match_id) {
        const got = await stackCall(
          `/api/stack/agentic/matches/${encodeURIComponent(last.match_id)}`
        );
        const match = got.data?.match || last;
        return NextResponse.json({
          ok: true,
          match_id: last.match_id,
          status: match?.status || "settled",
          match,
          last_settled: true,
        });
      }
      return NextResponse.json({ ok: true, match: null, match_id: "" });
    }
    const got = await stackCall(
      `/api/stack/agentic/matches/${encodeURIComponent(live.match_id)}`
    );
    const match = got.data?.match || null;
    return NextResponse.json({
      ok: true,
      match_id: live.match_id,
      status: match?.status || live.status,
      match,
    });
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
