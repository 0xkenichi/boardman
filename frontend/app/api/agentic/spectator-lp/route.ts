/**
 * Real LP deposit: debit the Telegram-linked Boardman profile, credit the
 * agent's LP pool. Goes through the gaming API which gates the spend behind
 * a Telegram approval (Yes / No / Always approve) unless the user has
 * pre-approved LP deposits.
 *
 * Requires rematch_session cookie (from Telegram Login Widget).
 */
import { NextRequest, NextResponse } from "next/server";
import { requireSession, rateLimitRequest } from "@/lib/bff";
import { stackConfigured, stackFetch } from "@/lib/stackServer";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const limited = rateLimitRequest(req, "spectator-lp", 20);
  if (limited) return limited;

  const auth = requireSession(req);
  if ("error" in auth) return auth.error;
  const { session } = auth;

  let body: { amount?: number; agent_id?: string; agent_name?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const amount = Number(body.amount);
  const agentId = String(body.agent_id || "").trim();
  const agentName = String(body.agent_name || "").trim();
  if (!Number.isFinite(amount) || amount < 0.25) {
    return NextResponse.json({ ok: false, error: "invalid_amount" }, { status: 400 });
  }
  if (!agentId) {
    return NextResponse.json({ ok: false, error: "invalid_agent" }, { status: 400 });
  }

  if (!stackConfigured()) {
    return NextResponse.json(
      {
        ok: false,
        error: "stack_not_configured",
        message: "Wallet backend offline — LP deposits need the gaming API.",
      },
      { status: 503 }
    );
  }

  const res = await stackFetch("/api/rematch/web/spectator/lp", {
    method: "POST",
    body: JSON.stringify({
      profile_id: session.profileId,
      amount,
      agent_id: agentId,
      agent_name: agentName,
    }),
  });

  const err = res.data?.error || res.data?.detail;
  if (res.ok && res.data?.success !== false) {
    return NextResponse.json({
      ok: true,
      pending: Boolean(res.data.pending),
      approval_id: res.data.approval_id || "",
      amount,
      agent_id: agentId,
      agent_name: agentName,
      balance: res.data.balance,
      address: res.data.address || "",
      lp_total_usdc: res.data.lp_total_usdc,
      message: res.data.message || "",
      profileId: session.profileId,
      tag: session.tag,
      name: session.name,
      source: "rematch_api",
    });
  }

  const errStr = String(err || "");
  if (errStr === "insufficient_balance" || errStr.startsWith("approval_")) {
    const status = errStr === "insufficient_balance" ? 400 : 403;
    return NextResponse.json(
      {
        ok: false,
        error: errStr,
        message: res.data?.message || "Could not deposit",
        balance: res.data?.balance,
        address: res.data?.address,
        approval_id: res.data?.approval_id,
      },
      { status }
    );
  }

  return NextResponse.json(
    {
      ok: false,
      error: err || "lp_failed",
      message: res.data?.message || "LP deposit failed",
    },
    { status: res.ok ? 500 : (res.status >= 400 && res.status < 600 ? res.status : 502) }
  );
}
