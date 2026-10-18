/**
 * The setup proof, browser side: before the passkey signs the server's
 * one-time challenge, check that the text really is about THIS wallet on
 * THIS chain (a page bug or a swapped response must never get a signature
 * for someone else's address). The server verifies the signature on chain
 * (ERC-1271 / ERC-6492) and binds it to the profile, the link and the time.
 */

export type SetupChallenge = {
  challenge_id: string
  message: string
  kind: 'setup' | 'change'
  evm_chain_id: number
  expires_at_ms: number
}

function field(message: string, name: string): string | null {
  for (const line of message.split('\n')) {
    if (line.startsWith(`${name}: `)) return line.slice(name.length + 2).trim()
  }
  return null
}

/** null when the challenge may be signed, else what is wrong with it. */
export function challengeProblem(c: SetupChallenge | null | undefined, address: string, chainId: number): string | null {
  if (!c || typeof c.message !== 'string' || typeof c.challenge_id !== 'string') return 'missing'
  const wallet = field(c.message, 'Wallet')
  if (!wallet || wallet.toLowerCase() !== address.toLowerCase()) return 'wallet'
  if (field(c.message, 'Chain ID') !== String(chainId) || c.evm_chain_id !== chainId) return 'chain'
  const purpose = field(c.message, 'Purpose')
  if (purpose !== c.kind || (purpose !== 'setup' && purpose !== 'change')) return 'purpose'
  if (!/^[0-9a-f]{32}$/.test(field(c.message, 'Nonce') || '')) return 'nonce'
  return null
}
