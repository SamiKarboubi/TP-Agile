import assert from 'node:assert/strict'
import { test } from 'node:test'
import { passwordRules } from '../src/passwordRules.js'
import { authenticateAccount } from '../src/authenticateAccount.js'

test('password feedback identifies every missing condition and accepts Unicode uppercase', () => {
  assert.deepEqual(passwordRules('abc').map((rule) => rule.valid), [false, true, false, false, false])
  assert.deepEqual(passwordRules('abcdef1!').map((rule) => rule.valid), [true, true, false, true, true])
  assert.deepEqual(passwordRules('Abcdefg!').map((rule) => rule.valid), [true, true, true, false, true])
  assert.deepEqual(passwordRules('Abcdef1 ').map((rule) => rule.valid), [true, true, true, true, false])
  assert.ok(passwordRules('Ébcdef1!').every((rule) => rule.valid))
  assert.ok(passwordRules('Abcdef1!' + 'x'.repeat(120)).every((rule) => rule.valid))
  assert.equal(passwordRules('Abcdef1!' + 'x'.repeat(121))[1].valid, false)
  assert.equal(passwordRules('A1!😀😀😀')[0].valid, false) // Six Unicode characters, not nine.
})

for (const mode of ['login', 'signup']) {
  test(`${mode} sends visitor favorites and retains only overflow`, async (t) => {
    t.mock.method(globalThis, 'fetch', async (url, options) => {
      assert.equal(url, `/api/auth/${mode}`)
      assert.equal(options.method, 'POST')
      assert.deepEqual(JSON.parse(options.body).favorite_ids, [1, 2, 3])
      return new Response(JSON.stringify({ user: { id: 'alice' }, favorite_ids: [2, 1, 4] }))
    })
    const visitor = [1, 2, 3]
    const { data, remaining } = await authenticateAccount(mode, 'alice', 'Abcdef1!', visitor)
    assert.deepEqual(data.favorite_ids, [2, 1, 4])
    assert.deepEqual(remaining, [3])
    assert.deepEqual(visitor, [1, 2, 3])
  })
}

test('failed authentication retains visitor favorites and displays the API error', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({
    detail: [{ msg: 'Value error, Il manque une lettre majuscule.', loc: ['body', 'password'] }],
  }), { status: 422 }))
  const visitor = [1, 2]
  await assert.rejects(authenticateAccount('signup', 'alice', 'abcdef1!', visitor), {
    message: 'Il manque une lettre majuscule.', status: 422,
  })
  assert.deepEqual(visitor, [1, 2])
})
