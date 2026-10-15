// The public /terms page is built from the counsel draft. These checks keep
// counsel's notes and repo-internal links off the public page, and keep the
// frontend copy identical to docs/. Run: cd frontend && node --test lib/__tests__/
import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontend = path.resolve(here, '../..')
const { parseMarkdown, parseInline, inlineText, safeHref } = await import('../legalMarkdown.ts')
const { publishTerms, OPERATOR_PLACEHOLDER } = await import('../legalTerms.ts')

const copy = fs.readFileSync(path.join(frontend, 'content/legal/TERMS_OF_SERVICE.md'), 'utf8')

test('frontend copy of the terms matches docs/TERMS_OF_SERVICE.md', () => {
  const source = path.resolve(frontend, '../docs/TERMS_OF_SERVICE.md')
  if (!fs.existsSync(source)) return // deployed from frontend/ alone
  assert.equal(copy, fs.readFileSync(source, 'utf8'), 'run: npm run sync:legal')
})

test('published terms carry no counsel notes, draft banner or repo links', () => {
  const out = publishTerms(copy)
  assert.doesNotMatch(out, /COUNSEL/)
  assert.doesNotMatch(out, /DRAFT|NOT LEGAL ADVICE/)
  assert.doesNotMatch(out, /\]\((?!https:\/\/|\/|mailto:)[^)]*\)/)
  assert.match(out, new RegExp(OPERATOR_PLACEHOLDER.replace(/[()]/g, '\\$&')))
  assert.match(out, /^## 19\. Contact/m)
})

test('every block of the published terms has text', () => {
  for (const b of parseMarkdown(publishTerms(copy))) {
    if (b.kind === 'heading' || b.kind === 'paragraph' || b.kind === 'quote') {
      assert.ok(inlineText(b.children).trim(), JSON.stringify(b))
    }
    if (b.kind === 'list') for (const item of b.items) assert.ok(inlineText(item).trim())
  }
})

test('the fee table survives as a table', () => {
  const table = parseMarkdown(publishTerms(copy)).find((b) => b.kind === 'table')
  assert.ok(table)
  assert.equal(table.head.length, 2)
  assert.equal(table.rows.length, 3)
})

test('unsafe links become plain text', () => {
  assert.equal(safeHref('javascript:alert(1)'), null)
  assert.equal(safeHref('//evil.example'), null)
  assert.equal(safeHref('http://plain.example'), null)
  assert.equal(safeHref('/privacy'), '/privacy')
  const nodes = parseInline('see [x](javascript:void) and <b>raw</b>')
  assert.ok(nodes.every((n) => n.kind === 'text'))
  assert.equal(inlineText(nodes), 'see x and <b>raw</b>')
})

test('inline bold, code and links parse', () => {
  const [strong, , code, , link] = parseInline('**bold** `code` [p](/privacy)')
  assert.equal(strong.kind, 'strong')
  assert.equal(code.kind, 'code')
  assert.equal(link.kind, 'link')
  assert.equal(link.href, '/privacy')
})
