/**
 * Read Arc testnet USDC balances via JSON-RPC eth_call (no private keys).
 */

const DEFAULT_RPC = 'https://rpc.testnet.arc.network'
const DEFAULT_USDC = '0x3600000000000000000000000000000000000000'

export function arcRpcUrl(): string {
  return (
    process.env.ARC_RPC_URL ||
    process.env.NEXT_PUBLIC_ARC_RPC_URL ||
    DEFAULT_RPC
  ).replace(/\/$/, '')
}

export function arcUsdcAddress(): string {
  return (
    process.env.ARC_USDC_ADDRESS ||
    process.env.NEXT_PUBLIC_ARC_USDC_ADDRESS ||
    DEFAULT_USDC
  )
}

function padAddress(addr: string): string {
  const hex = addr.replace(/^0x/i, '').toLowerCase()
  return hex.padStart(64, '0')
}

/** ERC-20 balanceOf → human USDC (6 decimals). */
export async function usdcBalanceOf(
  address: string,
  opts: { timeoutMs?: number } = {}
): Promise<{
  ok: boolean
  address: string
  balance_usdc: number
  raw?: string
  error?: string
  rpc?: string
}> {
  const addr = (address || '').trim()
  if (!/^0x[a-fA-F0-9]{40}$/.test(addr)) {
    return { ok: false, address: addr, balance_usdc: 0, error: 'invalid_address' }
  }
  const rpc = arcRpcUrl()
  const usdc = arcUsdcAddress()
  const data = `0x70a08231${padAddress(addr)}`
  try {
    const res = await fetch(rpc, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'BoardmanArena/onchain-balance',
      },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 1,
        method: 'eth_call',
        params: [{ to: usdc, data }, 'latest'],
      }),
      cache: 'no-store',
      signal: AbortSignal.timeout(opts.timeoutMs ?? 6000),
    })
    const json = (await res.json()) as { result?: string; error?: { message?: string } }
    if (!res.ok || json.error) {
      return {
        ok: false,
        address: addr,
        balance_usdc: 0,
        error: json.error?.message || `rpc_http_${res.status}`,
        rpc,
      }
    }
    const raw = json.result || '0x0'
    const n = BigInt(raw)
    const balance_usdc = Number(n) / 1e6
    return { ok: true, address: addr, balance_usdc, raw, rpc }
  } catch (e: any) {
    return {
      ok: false,
      address: addr,
      balance_usdc: 0,
      error: String(e?.message || e),
      rpc,
    }
  }
}
