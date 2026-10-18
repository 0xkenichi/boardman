/**
 * Minimal types for the passkey wallet SDK, used only while
 * `@circle-fin/modular-wallets-core` and `viem` are not installed. TypeScript
 * prefers the real packages' types once they are in node_modules (ambient
 * module declarations are a fallback), so this file can stay; delete it after
 * `npm i @circle-fin/modular-wallets-core viem` if you want to be sure.
 * Surface: docs/payments/SELF_CUSTODY_WALLETS.md §1 (Circle quickstart).
 */
declare module '@circle-fin/modular-wallets-core' {
  export const WebAuthnMode: { Register: any; Login: any }
  export function toPasskeyTransport(clientUrl: string, clientKey: string): any
  export function toWebAuthnCredential(args: { transport: any; mode: any; username?: string }): Promise<{ id: string } & Record<string, any>>
  export function toModularTransport(url: string, clientKey: string): any
  export function toCircleSmartAccount(args: { client: any; owner: any }): Promise<{ address: string } & Record<string, any>>
}

declare module 'viem' {
  export function defineChain<T>(chain: T): T
  export function createPublicClient(args: { chain: any; transport: any }): any
}

declare module 'viem/account-abstraction' {
  export function toWebAuthnAccount(args: { credential: any }): any
  export function createBundlerClient(args: { account: any; chain: any; transport: any }): {
    sendUserOperation(args: {
      calls: { to: `0x${string}`; data: `0x${string}`; value: bigint }[]
      paymaster?: true
    }): Promise<`0x${string}`>
    waitForUserOperationReceipt(args: { hash: `0x${string}` }): Promise<{
      success: boolean
      receipt: { transactionHash: `0x${string}` }
    }>
  }
}
