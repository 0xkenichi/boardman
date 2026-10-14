/**
 * Server-only: recover the signer address of an EIP-191 `personal_sign` message.
 *
 * Uses @noble/curves + @noble/hashes (audited, zero-dep) instead of ethers/viem.
 * Wallet signature format: 65 bytes r || s || v (v = 0/1 or 27/28).
 * noble's "recovered" format is recid || r || s — we convert between them.
 *
 * Verified round-trip: noble sign → wallet r||s||v → recover → keccak → address.
 */
import { secp256k1 } from '@noble/curves/secp256k1.js'
import { keccak_256 } from '@noble/hashes/sha3.js'

function eip191Digest(message: string): Uint8Array {
  const msg = Buffer.from(message, 'utf8')
  const prefix = Buffer.from(`\x19Ethereum Signed Message:\n${msg.length}`, 'utf8')
  return keccak_256(Buffer.concat([prefix, msg]))
}

/**
 * Recover the lowercase 0x address that signed `message`, or null if the
 * signature is malformed or does not verify (recovery is verification).
 */
export function recoverPersonalSignAddress(
  message: string,
  signatureHex: unknown
): string | null {
  if (typeof signatureHex !== 'string') return null
  const hex = signatureHex.startsWith('0x') ? signatureHex.slice(2) : signatureHex
  if (!/^[0-9a-fA-F]+$/.test(hex) || hex.length !== 130) return null

  try {
    const sig = Buffer.from(hex, 'hex')
    let v = sig[64]
    if (v >= 27) v -= 27
    if (v !== 0 && v !== 1) return null

    // wallet r||s||v → noble recid||r||s
    const nobleSig = Buffer.concat([Buffer.from([v]), sig.subarray(0, 64)])
    const compressed = secp256k1.recoverPublicKey(nobleSig, eip191Digest(message), {
      prehash: false,
    })
    const uncompressed = secp256k1.Point.fromBytes(compressed).toBytes(false)
    const hash = Buffer.from(keccak_256(uncompressed.slice(1)))
    return `0x${hash.toString('hex').slice(24)}`
  } catch {
    return null
  }
}
