/**
 * Public read of Arc testnet USDC balances for agent (or any) EOAs.
 * No secrets — eth_call only. Used by arena creator desk.
 *
 * GET ?addresses=0xabc,0xdef
 * or  ?raja=0x..&nero=0x..
 */
import { NextRequest, NextResponse } from 'next/server'
import { usdcBalanceOf, arcRpcUrl, arcUsdcAddress } from '@/lib/arcUsdc'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const DEMO = {
  raja: '0xDB131a4B88ACA79c29D5aDF3C3Df033954D36029',
  nero: '0xe430C73cF2beD38aBE83DF8309763191624373E1',
}

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams
  const list: { key: string; address: string }[] = []

  const bulk = sp.get('addresses')
  if (bulk) {
    bulk.split(',').forEach((a, i) => {
      const addr = a.trim()
      if (addr) list.push({ key: `a${i}`, address: addr })
    })
  }
  for (const key of ['raja', 'nero', 'agent_a', 'agent_b']) {
    const a = sp.get(key)
    if (a) list.push({ key, address: a.trim() })
  }
  if (!list.length) {
    list.push({ key: 'raja', address: DEMO.raja })
    list.push({ key: 'nero', address: DEMO.nero })
  }

  const results: Record<
    string,
    { address: string; balance_usdc: number; ok: boolean; error?: string }
  > = {}
  await Promise.all(
    list.map(async ({ key, address }) => {
      const r = await usdcBalanceOf(address)
      results[key] = {
        address: r.address,
        balance_usdc: r.balance_usdc,
        ok: r.ok,
        error: r.error,
      }
    })
  )

  return NextResponse.json({
    ok: true,
    chain: 'arc',
    network: 'testnet',
    source: 'arc_usdc_balanceOf',
    rpc: arcRpcUrl(),
    usdc: arcUsdcAddress(),
    balances: results,
    // augment with on-chain volume if backend exposes it
    volume: await (async () => {
      try {
        const base = process.env.STACK_API_URL || 'http://localhost:8000'
        const r = await fetch(`${base}/api/stack/agentic/agents/onchain_volume`, { cache: 'no-store' })
        if (!r.ok) return {}
        const j = await r.json()
        return j.totals || {}
      } catch (e) {
        return {}
      }
    })(),
    note: 'Agent bankrolls on creator desk should match these Arc testnet USDC balances when on-chain mode is live.',
  })
}
