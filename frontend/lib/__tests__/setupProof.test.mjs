// Setup proof: the browser's challenge check, and that the backend's Python
// ERC-6492 verifier (src/backend/services/self_custody/proof.py) builds the
// same bytes as viem's verifyMessage. The vectors below are asserted on the
// Python side too (tests/test_self_custody.py::test_proof_vectors_match_viem).
// Run: cd frontend && node --test lib/__tests__/
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  encodeDeployData,
  erc6492SignatureValidatorAbi,
  erc6492SignatureValidatorByteCode,
  hashMessage,
  keccak256,
  toBytes,
} from 'viem'

const { challengeProblem } = await import('../selfCustody/proof.ts')

const SA = '0x5a5A5a5a5A5a5a5a5a5A5a5A5A5a5a5A5A5A5A5A'
const MESSAGE = [
  'boardman.test wants you to prove you own this wallet.',
  '',
  'Link this wallet to my Boardman account.',
  '',
  `Wallet: ${SA}`,
  'Account: p_ada',
  'Chain ID: 5042002',
  'Purpose: setup',
  `Nonce: ${'0'.repeat(32)}`,
  'Issued At: 2025-10-09T08:53:20Z',
  'Expiration Time: 2025-10-09T09:03:20Z',
].join('\n')

test('python uses viem 2.57.7 ERC-6492 validator bytecode', () => {
  assert.equal(keccak256(erc6492SignatureValidatorByteCode), '0x00f03afb646c45f698b5a1f540c482aebc9f5215003e4707d362a02526753936')
})

test('python builds the same deployless validator call as viem', () => {
  const data = encodeDeployData({
    abi: erc6492SignatureValidatorAbi,
    bytecode: erc6492SignatureValidatorByteCode,
    args: [SA, keccak256(toBytes('boardman')), `0x${'11'.repeat(65)}`],
  })
  assert.equal((data.length - 2) / 2, 1908)
  assert.equal(keccak256(data), '0x922d78fbdbf2aa75561b64bf1b66899467a8004c22233d3d8db9b8d2b1ec1ab5')
})

test('python hashes the challenge like viem hashMessage (EIP-191)', () => {
  assert.equal(hashMessage(MESSAGE), '0xc81fcf8effc4b98b8f94567d2bf845e922a6d88a2959549583f338ad6bd7e173')
})

test('the page only signs a challenge for its own wallet and chain', () => {
  const c = { challenge_id: 'scw_1', message: MESSAGE, kind: 'setup', evm_chain_id: 5042002, expires_at_ms: 0 }
  assert.equal(challengeProblem(c, SA.toLowerCase(), 5042002), null)
  assert.equal(challengeProblem(c, '0x' + '66'.repeat(20), 5042002), 'wallet')
  assert.equal(challengeProblem(c, SA, 1), 'chain')
  assert.equal(challengeProblem({ ...c, kind: 'change' }, SA, 5042002), 'purpose')
  assert.equal(challengeProblem({ ...c, message: MESSAGE.replace(/Nonce: .*/, 'Nonce: x') }, SA, 5042002), 'nonce')
  assert.equal(challengeProblem(null, SA, 5042002), 'missing')
})
