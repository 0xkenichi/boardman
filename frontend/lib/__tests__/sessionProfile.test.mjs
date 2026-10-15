// "Mine" on the football owner pages follows the signed-in profile, not a
// hard-coded demo owner. Run: cd frontend && node --test lib/__tests__/
import { test } from 'node:test'
import assert from 'node:assert/strict'

const { loadSessionProfileId, ownedBy } = await import('../sessionProfile.ts')

const reply = (ok, body) => async () => ({ ok, json: async () => body })

test('signed-in session yields its profile id', async () => {
  assert.equal(await loadSessionProfileId(reply(true, { ok: true, profileId: 'tg_123' })), 'tg_123')
})

test('signed out, broken or unreachable session yields null', async () => {
  assert.equal(await loadSessionProfileId(reply(false, { ok: false })), null)
  assert.equal(await loadSessionProfileId(reply(true, { ok: true })), null)
  assert.equal(await loadSessionProfileId(async () => { throw new Error('offline') }), null)
})

test('ownedBy picks the signed-in owner and nobody else', () => {
  const agents = [
    { agent_id: 'a', owner_id: 'tg_123' },
    { agent_id: 'b', owner_id: 'demo_owner' },
    { agent_id: 'c', owner_id: null },
  ]
  assert.deepEqual(ownedBy(agents, 'tg_123').map((a) => a.agent_id), ['a'])
  // the old hard-coded demo owner is just another profile now
  assert.deepEqual(ownedBy(agents, null), [])
  assert.deepEqual(ownedBy(agents, undefined), [])
})
