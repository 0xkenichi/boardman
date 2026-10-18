/**
 * The player's passkey smart account (Circle Modular Wallets), in the browser.
 *
 * Follows Circle's quickstart (developers.circle.com/wallets/modular/
 * create-a-modular-wallet): passkey transport → WebAuthn credential →
 * modular transport for the chain → Circle smart account → bundler client.
 * The private key never leaves the player's authenticator; Boardman's server
 * never sees a signature it could replay, only the resulting tx hash.
 *
 * The SDK is loaded on demand. Until `npm i @circle-fin/modular-wallets-core
 * viem` has run, next.config.js aliases both to ./sdkMissing.ts and every
 * call here fails with `sdk_missing` (the pages then say "not available").
 */

export type ChainInfo = {
  chain: string
  label: string
  evm_chain_id: number
  rpc_url: string
  modular_path: string
  explorer_tx?: string
}

export type PreparedCall = { to: string; data: string; value: string; label?: string }

export class WalletError extends Error {
  code: string
  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

type Hex = `0x${string}`

const CLIENT_URL = process.env.NEXT_PUBLIC_CIRCLE_CLIENT_URL || 'https://modular-sdk.circle.com/v1/rpc/w3s/buidl'

function clientKey(): string {
  const k = process.env.NEXT_PUBLIC_CIRCLE_CLIENT_KEY || ''
  if (!k) throw new WalletError('not_configured', 'Passkey wallets are not switched on yet.')
  return k
}

export function walletsConfigured(): boolean {
  return Boolean(process.env.NEXT_PUBLIC_CIRCLE_CLIENT_KEY)
}

async function load() {
  try {
    const [sdk, viem, aa] = await Promise.all([
      import('@circle-fin/modular-wallets-core'),
      import('viem'),
      import('viem/account-abstraction'),
    ])
    return { sdk, viem, aa }
  } catch {
    throw new WalletError('sdk_missing', 'Passkey wallets are not switched on yet.')
  }
}

function friendly(e: unknown): WalletError {
  if (e instanceof WalletError) return e
  const name = (e as any)?.name || ''
  const msg = String((e as any)?.shortMessage || (e as any)?.message || e || '')
  if (name === 'NotAllowedError' || /not allowed|cancel|abort/i.test(msg)) {
    return new WalletError('cancelled', 'The passkey request was cancelled. Nothing was sent.')
  }
  if (/insufficient|exceeds balance/i.test(msg)) {
    return new WalletError('funds', 'Not enough USDC in your wallet for this.')
  }
  return new WalletError('failed', msg.slice(0, 200) || 'Something went wrong. Nothing was sent.')
}

async function account(info: ChainInfo, mode: 'register' | 'login', username: string) {
  const key = clientKey()
  const { sdk, viem, aa } = await load()
  const credential = await sdk.toWebAuthnCredential({
    transport: sdk.toPasskeyTransport(CLIENT_URL, key),
    mode: mode === 'register' ? sdk.WebAuthnMode.Register : sdk.WebAuthnMode.Login,
    username,
  })
  const chain = viem.defineChain({
    id: info.evm_chain_id,
    name: info.label,
    // Arc's native gas token is USDC (18-decimal native accounting).
    nativeCurrency: { name: 'USDC', symbol: 'USDC', decimals: 18 },
    rpcUrls: { default: { http: [info.rpc_url] } },
  })
  const transport = sdk.toModularTransport(`${CLIENT_URL}/${info.modular_path}`, key)
  const client = viem.createPublicClient({ chain, transport })
  const smart = await sdk.toCircleSmartAccount({ client, owner: aa.toWebAuthnAccount({ credential }) })
  return { credential, smart, chain, transport, aa }
}

/** Create a passkey and read the (counterfactual) smart-account address. */
export async function createWallet(info: ChainInfo, username: string): Promise<{ address: string; credentialId: string }> {
  try {
    const { credential, smart } = await account(info, 'register', username)
    return { address: smart.address, credentialId: credential.id }
  } catch (e) {
    throw friendly(e)
  }
}

/**
 * Sign the prepared calls with the player's passkey as ONE UserOperation and
 * wait for it to land. Refuses if the passkey opens a different wallet than
 * the one Boardman expects (so a player with two passkeys can't send from the
 * wrong account).
 */
export async function approveCalls(
  info: ChainInfo,
  expectedAccount: string,
  calls: PreparedCall[],
  sponsorGas: boolean,
  username: string,
): Promise<{ userOpHash: string; txHash: string; success: boolean }> {
  try {
    const { smart, chain, transport, aa } = await account(info, 'login', username)
    if (smart.address.toLowerCase() !== expectedAccount.toLowerCase()) {
      throw new WalletError('wrong_wallet', 'That passkey opens a different wallet than the one linked to your Boardman account.')
    }
    const bundler = aa.createBundlerClient({ account: smart, chain, transport })
    const userOpHash = await bundler.sendUserOperation({
      calls: calls.map((c) => ({ to: c.to as Hex, data: c.data as Hex, value: BigInt(c.value || '0') })),
      paymaster: sponsorGas ? true : undefined,
    })
    const { receipt, success } = await bundler.waitForUserOperationReceipt({ hash: userOpHash })
    return { userOpHash, txHash: receipt.transactionHash, success: Boolean(success) }
  } catch (e) {
    throw friendly(e)
  }
}
