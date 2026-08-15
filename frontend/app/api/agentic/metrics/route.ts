/**
 * Operator-only live book. No static snapshot. Telegram ID gate.
 */
import { NextRequest, NextResponse } from "next/server";
import { rematchApiFetch } from "@/lib/stackServer";
import { requireAdmin } from "@/lib/adminAuth";
import fs from "fs";
import path from "path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const RAJA = "agent_raja_kia_alekhine";
const NERO = "agent_nero_sicilian_french";
const NAMES: Record<string, string> = { [RAJA]: "Raja", [NERO]: "Nero" };
const EXPLORER = "https://testnet.arcscan.app/tx/";

function q6(n: number): string {
  return (Math.round(n * 1e6) / 1e6).toFixed(6);
}

function findMatchesPath(): string | null {
  const env = process.env.BOARDMAN_AGENTIC_DATA;
  if (env) {
    const p = path.join(env, "matches.json");
    if (fs.existsSync(p)) return p;
  }
  const cwd = process.cwd();
  const candidates = [
    path.resolve(cwd, "data/agentic/matches.json"),
    path.resolve(cwd, "../data/agentic/matches.json"),
    path.resolve(cwd, "../../data/agentic/matches.json"),
  ];
  return candidates.find((p) => fs.existsSync(p)) || null;
}

function skillPnl(m: any, agentId: string): number {
  if (m.status !== "settled") return 0;
  const stake = Number(m.stake_usdc || 0);
  const result = String(m.result || "").toLowerCase();
  const winner = m.winner_agent_id;
  if (result === "draw" || result === "1/2-1/2" || !winner) return 0;
  if (agentId === winner) {
    const split = m.fee_split || m.escrow?.fee_split || {};
    const payout = Number(split.owner_payout || 0);
    if (payout > 0) return payout - stake;
    return stake * 2 * 0.97 - stake;
  }
  if (agentId === m.agent_a_id || agentId === m.agent_b_id) return -stake;
  return 0;
}

function proofs(m: any) {
  const onchain = m.onchain || {};
  const settle = m.onchain_settle || m.escrow?.onchain_settle || {};
  const txs = (onchain.txs || [])
    .filter((t: any) => t?.tx_hash)
    .map((t: any) => ({
      step: t.step || "",
      tx_hash: t.tx_hash,
      explorer: t.explorer || EXPLORER + t.tx_hash,
    }));
  const settleHash = settle.tx_hash || "";
  if (settleHash && !txs.some((t: any) => t.tx_hash === settleHash)) {
    txs.push({
      step: "resolveMatch",
      tx_hash: settleHash,
      explorer: settle.explorer || EXPLORER + settleHash,
    });
  }
  const createH = onchain.create_tx_hash || "";
  const joinH = onchain.join_tx_hash || "";
  return {
    chain_id: m.chain_id || onchain.chain_id || "arc",
    settlement_mode: m.settlement_mode || (createH ? "onchain" : "demo_ledger"),
    escrow: onchain.escrow || "",
    match_id_bytes32: m.match_id_bytes32 || onchain.match_id_bytes32 || "",
    create_tx_hash: createH,
    join_tx_hash: joinH,
    settle_tx_hash: settleHash,
    explorer_create: onchain.explorer_create || (createH ? EXPLORER + createH : ""),
    explorer_join: onchain.explorer_join || (joinH ? EXPLORER + joinH : ""),
    explorer_settle: settle.explorer || (settleHash ? EXPLORER + settleHash : ""),
    txs,
    settle_error: m.onchain_settle_error || "",
  };
}

function emptyCard(id: string) {
  return {
    agent_id: id,
    name: NAMES[id] || id,
    wallet: "",
    played: 0,
    wins: 0,
    losses: 0,
    draws: 0,
    white_games: 0,
    black_games: 0,
    skill_pnl_usdc: "0.000000",
    stake_volume_usdc: "0.000000",
    seed_spent_usdc: "0.000000",
    lp_realized_pnl_usdc: "0.000000",
    onchain_locks: 0,
    _pnl: 0,
    _stake: 0,
    _seed: 0,
  };
}

function aggregateFromFile(limit: number) {
  const file = findMatchesPath();
  if (!file) return null;
  const store = JSON.parse(fs.readFileSync(/*turbopackIgnore: true*/ file, "utf8"));
  const rows: any[] = Object.values(store.matches || {});
  rows.sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));

  const cards: Record<string, any> = {
    [RAJA]: emptyCard(RAJA),
    [NERO]: emptyCard(NERO),
  };
  let skillVol = 0;
  let specVol = 0;
  let settled = 0;
  let locked = 0;
  let onchainN = 0;
  let liveN = 0;
  const txSeen = new Set<string>();
  const txByStep: Record<string, number> = {};
  const txRows: any[] = [];
  const publicRows: any[] = [];

  const addTx = (hash: string, step: string, matchId: string) => {
    const h = String(hash || "").trim();
    if (!h || txSeen.has(h)) return;
    txSeen.add(h);
    txByStep[step || "tx"] = (txByStep[step || "tx"] || 0) + 1;
    txRows.push({
      tx_hash: h,
      step: step || "tx",
      match_id: matchId,
      explorer: EXPLORER + h,
      created_at: "",
    });
  };

  for (const m of rows) {
    const stake = Number(m.stake_usdc || 0);
    if (m.status === "settled" || m.status === "locked") skillVol += stake * 2;
    if (m.status === "settled") settled += 1;
    if (m.status === "locked") locked += 1;
    if (["playing", "locking", "locked", "open"].includes(String(m.status || ""))) liveN += 1;
    if (m.settlement_mode === "onchain" || m.onchain?.create_tx_hash) onchainN += 1;
    const p = proofs(m);
    addTx(p.create_tx_hash, "lock", m.match_id);
    addTx(p.join_tx_hash, "join", m.match_id);
    addTx(p.settle_tx_hash, "settle", m.match_id);
    for (const t of p.txs || []) addTx(t.tx_hash, t.step || "tx", m.match_id);
    const book = m.spectator_book || {};
    addTx(book.open_tx_hash, "openBook", m.match_id);
    addTx(book.resolve_tx_hash, "resolveBook", m.match_id);
    const totals = m.spectator_book?.totals || {};
    specVol += Number(totals.a || 0) + Number(totals.b || 0);

    for (const aid of [m.agent_a_id, m.agent_b_id]) {
      if (!aid) continue;
      if (!cards[aid]) cards[aid] = emptyCard(aid);
      const c = cards[aid];
      if (m.status === "settled" || m.status === "locked") c._stake += stake;
      if (m.status === "settled") {
        c.played += 1;
        const winner = m.winner_agent_id;
        const result = String(m.result || "").toLowerCase();
        if (result === "draw" || result === "1/2-1/2" || !winner) c.draws += 1;
        else if (winner === aid) c.wins += 1;
        else c.losses += 1;
        if (m.white_agent_id === aid) c.white_games += 1;
        if (m.black_agent_id === aid) c.black_games += 1;
        c._pnl += skillPnl(m, aid);
        const book = m.spectator_book || {};
        if (book.payouts?.mode !== "refund") {
          const eco = m.economy || {};
          c._seed += Number(
            aid === m.agent_a_id ? eco.spectator_seed_a || book.seed_a : eco.spectator_seed_b || book.seed_b
          ) || 0;
        }
      }
      if (m.onchain?.create_tx_hash) c.onchain_locks += 1;
    }

    if (publicRows.length < limit) {
      const pgn = m.pgn || "";
      publicRows.push({
        match_id: m.match_id,
        game_id: m.game_id || "agentic.chess_standard",
        status: m.status,
        result: m.result,
        termination: m.termination,
        stake_usdc: q6(stake),
        created_at: m.created_at,
        settled_at: m.settled_at || m.escrow?.settled_at,
        white: {
          agent_id: m.white_agent_id,
          name: NAMES[m.white_agent_id] || m.white_agent_id,
          wallet: m.white_agent_id === m.agent_a_id ? m.agent_a_wallet : m.agent_b_wallet,
        },
        black: {
          agent_id: m.black_agent_id,
          name: NAMES[m.black_agent_id] || m.black_agent_id,
          wallet: m.black_agent_id === m.agent_a_id ? m.agent_a_wallet : m.agent_b_wallet,
        },
        winner: m.winner_agent_id
          ? { agent_id: m.winner_agent_id, name: NAMES[m.winner_agent_id] || m.winner_agent_id }
          : null,
        proofs: proofs(m),
        spectator: {
          status: m.spectator_book?.status,
          pot_usdc: q6(Number(m.spectator_book?.totals?.a || 0) + Number(m.spectator_book?.totals?.b || 0)),
          mode: m.spectator_book?.payouts?.mode,
          ledger_only: true,
        },
        skill_pnl: {
          a: q6(skillPnl(m, m.agent_a_id)),
          b: q6(skillPnl(m, m.agent_b_id)),
        },
        pgn_preview: pgn.length > 160 ? pgn.slice(0, 160) + "…" : pgn,
      });
    }
  }

  const agents = Object.values(cards).map((c: any) => {
    c.skill_pnl_usdc = q6(c._pnl);
    c.stake_volume_usdc = q6(c._stake);
    c.seed_spent_usdc = q6(c._seed);
    delete c._pnl;
    delete c._stake;
    delete c._seed;
    return c;
  });
  agents.sort((a: any, b: any) => {
    const o: Record<string, number> = { [RAJA]: 0, [NERO]: 1 };
    return (o[a.agent_id] ?? 9) - (o[b.agent_id] ?? 9);
  });

  return {
    success: true,
    generated_at: new Date().toISOString(),
    source: "matches.json",
    note:
      "Skill lock/settle proofs are on-chain when settlement_mode=onchain. Spectator bets and LP deposits are internal-ledger (no spectator pool contract).",
    volume: {
      matches_total: rows.length,
      matches_settled: settled,
      matches_locked: locked,
      matches_onchain: onchainN,
      games_played: settled + liveN,
      games_settled: settled,
      games_live: liveN,
      transactions: txSeen.size,
      tx_by_step: txByStep,
      skill_volume_usdc: q6(skillVol),
      spectator_volume_usdc: q6(specVol),
    },
    agents,
    matches: publicRows,
    transactions: txRows.slice(0, Math.min(200, limit * 3)),
  };
}

export async function GET(req: NextRequest) {
  const auth = requireAdmin(req);
  if ("error" in auth) return auth.error;

  const limit = Math.max(1, Math.min(Number(req.nextUrl.searchParams.get("limit") || 100), 200));
  const headers = { "Cache-Control": "no-store" };

  const remote = await Promise.race([
    rematchApiFetch(`/api/stack/agentic/public/metrics?limit=${limit}`),
    new Promise<{ ok: false; status: number; data: any }>((resolve) =>
      setTimeout(() => resolve({ ok: false, status: 504, data: { error: "timeout" } }), 8000)
    ),
  ]);
  if (remote.ok && remote.data?.success) {
    return NextResponse.json({ ...remote.data, via: "stack_api" }, { headers });
  }

  const local = aggregateFromFile(limit);
  if (local) {
    return NextResponse.json({ ...local, via: "local_matches_json" }, { headers });
  }

  return NextResponse.json(
    {
      success: true,
      generated_at: new Date().toISOString(),
      via: "empty",
      note: remote.data?.error || "House API offline — no live book.",
      volume: {
        matches_total: 0,
        matches_settled: 0,
        matches_locked: 0,
        matches_onchain: 0,
        skill_volume_usdc: "0",
        spectator_volume_usdc: "0",
      },
      agents: [],
      matches: [],
    },
    { headers }
  );
}
