/**
 * The chain this build settles on, for links and labels on the site.
 *
 * NEXT_PUBLIC_SETTLEMENT_CHAIN picks it at build time: `avalanche` (default,
 * Avalanche Fuji C-Chain) or `arc` (Arc testnet, kept for the multi-chain code).
 * Mirrors config/chains.yaml; the escrow addresses there are the source.
 */

export type SettlementChain = {
  id: 'arc' | 'avalanche'
  label: string
  /** Upper-case strap for the ledger rules on the homepage. */
  strap: string
  chainId: number
  gasToken: string
  usdc: string
  escrow: string
  explorerName: string
  explorerAddress: string
  explorerTx: string
}

const CHAINS: Record<SettlementChain['id'], SettlementChain> = {
  // BoardmanEscrow V1 (tiered fees). 0xD898…66Fc is the archived flat-fee V1.
  arc: {
    id: 'arc',
    label: 'Arc testnet',
    strap: 'ARC TESTNET · CHAIN 5042002 · USDC-NATIVE GAS',
    chainId: 5042002,
    gasToken: 'USDC',
    usdc: '0x3600000000000000000000000000000000000000',
    escrow: '0xD382f627fB565eb96D9EFFb66B9119DD4a555847',
    explorerName: 'Arcscan',
    explorerAddress: 'https://explorer.testnet.arc.io/address/',
    explorerTx: 'https://explorer.testnet.arc.io/tx/',
  },
  // BoardmanEscrow v2 (contracts/deployments/boardman_v2_avalancheFuji.json).
  avalanche: {
    id: 'avalanche',
    label: 'Avalanche Fuji',
    strap: 'AVALANCHE FUJI C-CHAIN · CHAIN 43113 · CIRCLE USDC',
    chainId: 43113,
    gasToken: 'AVAX',
    usdc: '0x5425890298aed601595a70AB815c96711a31Bc65',
    escrow: '0xa0626A1744D4817B8b6fE0414a04CB20F6696F09',
    explorerName: 'Snowtrace',
    explorerAddress: 'https://testnet.snowtrace.io/address/',
    explorerTx: 'https://testnet.snowtrace.io/tx/',
  },
}

export function settlementChain(): SettlementChain {
  const id = (process.env.NEXT_PUBLIC_SETTLEMENT_CHAIN || 'avalanche').trim().toLowerCase()
  return CHAINS[id as SettlementChain['id']] ?? CHAINS.avalanche
}

export const SETTLEMENT = settlementChain()

export const shortAddress = (a: string) => `${a.slice(0, 6)}…${a.slice(-4)}`
