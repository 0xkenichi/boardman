/**
 * Stand-in for `@circle-fin/modular-wallets-core` and `viem` until they are
 * installed (next.config.js aliases them here only when they can't be
 * resolved). Every export throws, so the passkey pages show
 * "not available yet" instead of the build failing.
 */
function missing(): never {
  throw new Error('sdk_missing')
}

export const WebAuthnMode = { Register: 'register', Login: 'login' }
export const toPasskeyTransport = missing
export const toWebAuthnCredential = missing
export const toModularTransport = missing
export const toCircleSmartAccount = missing
export const createPublicClient = missing
export const defineChain = missing
export const createBundlerClient = missing
export const toWebAuthnAccount = missing
