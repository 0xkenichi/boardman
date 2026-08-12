/**
 * Debit the Telegram-linked Boardman profile for an arena spectator bet.
 * Requires rematch_session cookie (from Telegram Login Widget).
 *
 * 1) Prefer gaming API /api/rematch/web/spectator/bet
 * 2) Fallback: Supabase profiles.wallet_balance_usdc debit
 *    (sync from Arc play address if ledger is empty but on-chain has funds)
 */
import { NextRequest, NextResponse } from "next/server";
import { requireSession, rateLimitRequest } from "@/lib/bff";
import { stackConfigured, stackFetch } from "@/lib/stackServer";
import { fetchProfileWallet, supabaseRest } from "@/lib/supabaseAdmin";
import { usdcBalanceOf } from "@/lib/arcUsdc";

export const dynamic = "force-dynamic";

async function debitViaSupabase(
  profileId: string,
  amount: number
): Promise<{ ok: boolean; balance?: number; address?: string; error?: string; source?: string }> {
  const row = await fetchProfileWallet(profileId);
  if (!row) {
    return { ok: false, error: "profile_not_found" };
  }

  const address = (
    row.gaming_deposit_address ||
    row.wallet_address ||
    row.linked_wallet ||
    ""
  )
    .trim()
    .toLowerCase();

  let ledger = Number(row.wallet_balance_usdc ?? 0);
  let onchain = 0;
  if (address && /^0x[a-f0-9]{40}$/.test(address)) {
    const r = await usdcBalanceOf(address);
    if (r.ok) onchain = Number(r.balance_usdc) || 0;
  }

  // Spendable for arena: ledger, or on-chain play address if ledger lags
  let spendable = Math.max(ledger, onchain);
  if (spendable + 1e-9 < amount) {
    return {
      ok: false,
      error: "insufficient_balance",
      balance: spendable,
      address,
    };
  }

  // If ledger is behind on-chain, sync ledger up so we can debit in DB
  // (full chain transfer still requires gaming API / Circle later)
  if (ledger + 1e-9 < amount && onchain >= amount) {
    const sync = await supabaseRest(
      `profiles?id=eq.${encodeURIComponent(profileId)}`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Prefer: "return=representation",
        },
        body: JSON.stringify({ wallet_balance_usdc: onchain }),
      }
    );
    if (!sync.ok) {
      return {
        ok: false,
        error: "ledger_sync_failed",
        balance: onchain,
        address,
      };
    }
    ledger = onchain;
  }

  const next = Math.round((ledger - amount) * 1e6) / 1e6;
  if (next < -1e-9) {
    return { ok: false, error: "insufficient_balance", balance: ledger, address };
  }

  const patch = await supabaseRest(
    `profiles?id=eq.${encodeURIComponent(profileId)}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Prefer: "return=representation",
      },
      body: JSON.stringify({ wallet_balance_usdc: next }),
    }
  );
  if (!patch.ok) {
    return {
      ok: false,
      error: "debit_failed",
      balance: ledger,
      address,
    };
  }

  // Best-effort audit row (ignore if table missing)
  try {
    await supabaseRest("wallet_credit_audit", {
      method: "POST",
      headers: { "Content-Type": "application/json", Prefer: "return=minimal" },
      body: JSON.stringify({
        profile_id: profileId,
        amount: -amount,
        reason: "arena_spectator_bet",
        source: "vercel_bff",
        created_at: new Date().toISOString(),
      }),
    });
  } catch {
    /* optional table */
  }

  return {
    ok: true,
    balance: next,
    address,
    source: onchain > ledger + 0.001 ? "supabase_synced_from_arc" : "supabase_ledger",
  };
}

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

  // 1) Gaming API when rematch routes exist
  if (stackConfigured()) {
    const res = await stackFetch("/api/rematch/web/spectator/bet", {
      method: "POST",
      body: JSON.stringify({
        profile_id: session.profileId,
        amount,
        side,
        match_id: body.match_id || "arena",
      }),
    });

    if (res.ok && res.data?.success !== false && res.data?.balance != null) {
      return NextResponse.json({
        ok: true,
        amount,
        side,
        balance: res.data.balance,
        address: res.data.address || res.data.wallet || "",
        profileId: session.profileId,
        tag: session.tag,
        name: session.name,
        source: "rematch_api",
      });
    }

    // If API returned a clear business error (insufficient, etc.), surface it
    const err = res.data?.error || res.data?.detail;
    if (res.ok && err === "insufficient_balance") {
      return NextResponse.json(
        {
          ok: false,
          error: "insufficient_balance",
          message: res.data?.message || "Not enough USDC",
          balance: res.data?.balance,
          address: res.data?.address,
        },
        { status: 400 }
      );
    }
    // else fall through to Supabase (404 / wrong host / 502)
    console.warn(
      "[spectator-bet] stack path failed status=%s err=%s — trying supabase",
      res.status,
      err
    );
  }

  // 2) Supabase + Arc balance fallback
  const local = await debitViaSupabase(session.profileId, amount);
  if (!local.ok) {
    return NextResponse.json(
      {
        ok: false,
        error: local.error || "bet_failed",
        message:
          local.error === "insufficient_balance"
            ? "Not enough USDC on your Boardman wallet. Fund via Telegram → Get money."
            : "Could not place bet from wallet",
        balance: local.balance,
        address: local.address,
      },
      { status: 400 }
    );
  }

  return NextResponse.json({
    ok: true,
    amount,
    side,
    balance: local.balance,
    address: local.address || "",
    profileId: session.profileId,
    tag: session.tag,
    name: session.name,
    source: local.source || "supabase_ledger",
  });
}
