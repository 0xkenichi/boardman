/**
 * MiniPay (Celo / Opera) host detection helpers.
 * @see https://docs.celo.org/developer/build-on-minipay
 */

export const CELO_MAINNET_CHAIN_ID = 42220
export const CELO_ALFAJORES_CHAIN_ID = 44787

export type MiniPayState = {
  isMiniPay: boolean
  host: 'minipay' | 'browser' | 'telegram' | 'unknown'
  address: string | null
  chainId: number | null
  error: string | null
}

declare global {
  interface Window {
    ethereum?: {
      isMiniPay?: boolean
      isMetaMask?: boolean
      request: (args: { method: string; params?: unknown[] }) => Promise<unknown>
      on?: (event: string, handler: (...args: any[]) => void) => void
      removeListener?: (event: string, handler: (...args: any[]) => void) => void
    }
    Telegram?: { WebApp?: { initData?: string } }
  }
}

export function detectHost(): MiniPayState['host'] {
  if (typeof window === 'undefined') return 'unknown'
  try {
    if (window.ethereum?.isMiniPay) return 'minipay'
    if (window.Telegram?.WebApp?.initData) return 'telegram'
    const q = new URLSearchParams(window.location.search)
    if (q.get('host') === 'minipay') return 'minipay'
  } catch {
    /* ignore */
  }
  return 'browser'
}

export function isMiniPayEnvironment(): boolean {
  if (typeof window === 'undefined') return false
  if (window.ethereum?.isMiniPay) return true
  try {
    return new URLSearchParams(window.location.search).get('host') === 'minipay'
  } catch {
    return false
  }
}

export async function readMiniPayState(): Promise<MiniPayState> {
  const host = detectHost()
  const eth = typeof window !== 'undefined' ? window.ethereum : undefined
  const isMiniPay = Boolean(eth?.isMiniPay) || host === 'minipay'

  if (!eth) {
    return {
      isMiniPay,
      host,
      address: null,
      chainId: null,
      error: isMiniPay
        ? 'MiniPay provider not injected yet — open this URL inside MiniPay.'
        : null,
    }
  }

  try {
    const accounts = (await eth.request({ method: 'eth_accounts' })) as string[]
    let address = accounts?.[0] || null
    if (!address && isMiniPay) {
      // Request only when we know we're in MiniPay (avoid MetaMask popup spam)
      const req = (await eth.request({ method: 'eth_requestAccounts' })) as string[]
      address = req?.[0] || null
    }
    const chainHex = (await eth.request({ method: 'eth_chainId' })) as string
    const chainId = chainHex ? parseInt(chainHex, 16) : null
    return { isMiniPay, host, address, chainId, error: null }
  } catch (e: any) {
    return {
      isMiniPay,
      host,
      address: null,
      chainId: null,
      error: String(e?.message || e || 'provider_error'),
    }
  }
}

export function chainLabel(chainId: number | null): string {
  if (chainId === CELO_MAINNET_CHAIN_ID) return 'Celo'
  if (chainId === CELO_ALFAJORES_CHAIN_ID) return 'Celo Alfajores'
  if (chainId == null) return '—'
  return `chain ${chainId}`
}

/** MiniPay listing / deep-link entry for Rematch */
export const MINIPAY_ENTRY_URL =
  process.env.NEXT_PUBLIC_MINIPAY_ENTRY_URL ||
  'https://boardman.playingsidequest.fun/app?host=minipay'
