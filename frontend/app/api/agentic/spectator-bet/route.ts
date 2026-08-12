/**
 * Debit the Telegram-linked Boardman profile wallet for an arena spectator bet.
 * Requires rematch_session cookie (from Telegram Login Widget).
 */
import { NextRequest, NextResponse } from "next/server";
import { requireSession } from "@/lib/bff";
import { stackConfigured, stackFetch } from "@/lib/stackServer";
import { rateLimitRequest } from "@/lib/bff";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const limited = rateLimitRequest(req, "spectator-bet", 20);
  if (limited) return limited;

  const auth = requireSession(req);
  if ("error" in auth) return auth.error;
  const { session } = auth;

  let body: { amount?: number; side?: string; match_id?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const amount = Number(body.amount);
  let side = String(body.side || "").toLowerCase();
  if (side === "raja" || side === "white") side = "a";
  if (side === "nero" || side === "black") side = "b";
  if (!Number.isFinite(amount) || amount < 0.25) {
    return NextResponse.json({ ok: false, error: "invalid_amount" }, { status: 400 });
  }
  if (side !== "a" && side !== "b") {
    return NextResponse.json({ ok: false, error: "invalid_side" }, { status: 400 });
  }

  if (!stackConfigured()) {
    return NextResponse.json(
      {
        ok: false,
        error: "stack_not_configured",
        message:
          "Live wallet debits need REMATCH_API_URL + REMATCH_API_KEY on the web host. Session is valid but balance API is offline.",
        profileId: session.profileId,
        tag: session.tag,
      },
      { status: 503 }
    );
  }

  const res = await stackFetch("/api/rematch/web/spectator/bet", {
    method: "POST",
    body: JSON.stringify({
      profile_id: session.profileId,
      amount,
      side,
      match_id: body.match_id || "arena",
    }),
  });

  if (!res.ok || res.data?.success === false) {
    const err = res.data?.error || res.data?.detail || "bet_failed";
    return NextResponse.json(
      {
        ok: false,
        error: err,
        message: res.data?.message || res.data?.detail || "Could not place bet",
        balance: res.data?.balance,
        address: res.data?.address,
      },
      { status: res.status === 503 ? 503 : 400 }
    );
  }

  return NextResponse.json({
    ok: true,
    amount,
    side,
    balance: res.data.balance,
    address: res.data.address || res.data.wallet || "",
    profileId: session.profileId,
    tag: session.tag,
    name: session.name,
  });
}
