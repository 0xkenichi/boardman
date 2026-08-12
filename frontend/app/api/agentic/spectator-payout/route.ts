/**
 * Credit spectator winnings/refund to the Telegram-linked Boardman wallet.
 */
import { NextRequest, NextResponse } from "next/server";
import { requireSession, rateLimitRequest } from "@/lib/bff";
import { stackConfigured, stackFetch } from "@/lib/stackServer";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const limited = rateLimitRequest(req, "spectator-payout", 20);
  if (limited) return limited;

  const auth = requireSession(req);
  if ("error" in auth) return auth.error;
  const { session } = auth;

  let body: { amount?: number; reason?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }
  const amount = Number(body.amount);
  if (!Number.isFinite(amount) || amount <= 0) {
    return NextResponse.json({ ok: false, error: "invalid_amount" }, { status: 400 });
  }
  if (!stackConfigured()) {
    return NextResponse.json({ ok: false, error: "stack_not_configured" }, { status: 503 });
  }

  const res = await stackFetch("/api/rematch/web/spectator/payout", {
    method: "POST",
    body: JSON.stringify({
      profile_id: session.profileId,
      amount,
      reason: body.reason || "spectator_payout",
    }),
  });

  if (!res.ok || res.data?.success === false) {
    return NextResponse.json(
      { ok: false, error: res.data?.detail || res.data?.error || "payout_failed" },
      { status: 400 }
    );
  }

  return NextResponse.json({
    ok: true,
    amount,
    balance: res.data.balance,
    profileId: session.profileId,
  });
}
