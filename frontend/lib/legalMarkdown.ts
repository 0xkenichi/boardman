/**
 * A deliberately small Markdown reader for the legal pages.
 *
 * It understands only what docs/TERMS_OF_SERVICE.md uses: headings,
 * paragraphs, bullet lists, pipe tables, blockquotes, rules, and inline
 * bold, italic, code and links. It returns plain data (no HTML strings), so
 * React escapes every piece of text when the page renders it. Anything it
 * does not recognise stays literal text.
 *
 * No imports and erasable-only TypeScript, so `node --test` can load it.
 */

export type Inline =
  | { kind: 'text'; text: string }
  | { kind: 'strong'; children: Inline[] }
  | { kind: 'em'; children: Inline[] }
  | { kind: 'code'; text: string }
  | { kind: 'link'; href: string; children: Inline[] }

export type Block =
  | { kind: 'heading'; level: number; children: Inline[] }
  | { kind: 'paragraph'; children: Inline[] }
  | { kind: 'list'; items: Inline[][] }
  | { kind: 'table'; head: Inline[][]; rows: Inline[][][] }
  | { kind: 'quote'; children: Inline[] }
  | { kind: 'rule' }

/** Only same-site paths, https and mailto links survive; others become text. */
export function safeHref(href: string): string | null {
  const h = href.trim()
  if (/^\/(?!\/)/.test(h)) return h
  if (/^https:\/\/[^\s]+$/i.test(h)) return h
  if (/^mailto:[^\s@]+@[^\s@]+$/i.test(h)) return h
  return null
}

export function parseInline(src: string): Inline[] {
  const out: Inline[] = []
  let buf = ''
  const flush = () => {
    if (buf) out.push({ kind: 'text', text: buf })
    buf = ''
  }
  let i = 0
  while (i < src.length) {
    const rest = src.slice(i)
    let m: RegExpMatchArray | null
    if ((m = rest.match(/^`([^`]+)`/))) {
      flush()
      out.push({ kind: 'code', text: m[1] })
      i += m[0].length
    } else if ((m = rest.match(/^\*\*([\s\S]+?)\*\*/))) {
      flush()
      out.push({ kind: 'strong', children: parseInline(m[1]) })
      i += m[0].length
    } else if ((m = rest.match(/^\*([^*\s][^*]*?)\*/))) {
      flush()
      out.push({ kind: 'em', children: parseInline(m[1]) })
      i += m[0].length
    } else if ((m = rest.match(/^\[([^\]]+)\]\(([^)\s]+)\)/))) {
      flush()
      const href = safeHref(m[2])
      const children = parseInline(m[1])
      if (href) out.push({ kind: 'link', href, children })
      else out.push(...children)
      i += m[0].length
    } else {
      buf += src[i]
      i += 1
    }
  }
  flush()
  return out
}

const isRule = (l: string) => /^\s*(?:-{3,}|\*{3,})\s*$/.test(l)
const isHeading = (l: string) => /^#{1,6}\s/.test(l)
const isBullet = (l: string) => /^\s*[-*]\s+/.test(l)
const isTableRow = (l: string) => /^\s*\|.*\|\s*$/.test(l)
const isTableSep = (l: string) => /^\s*\|(?:\s*:?-{2,}:?\s*\|)+\s*$/.test(l)
const isQuote = (l: string) => /^\s*>/.test(l)

function cells(row: string): string[] {
  return row
    .trim()
    .replace(/^\||\|$/g, '')
    .split('|')
    .map((c) => c.trim())
}

export function parseMarkdown(md: string): Block[] {
  const lines = md.replace(/\r\n?/g, '\n').split('\n')
  const blocks: Block[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) {
      i += 1
      continue
    }
    if (isRule(line)) {
      blocks.push({ kind: 'rule' })
      i += 1
      continue
    }
    const h = line.match(/^(#{1,6})\s+(.*)$/)
    if (h) {
      blocks.push({ kind: 'heading', level: h[1].length, children: parseInline(h[2].trim()) })
      i += 1
      continue
    }
    if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const head = cells(line).map(parseInline)
      i += 2
      const rows: Inline[][][] = []
      while (i < lines.length && isTableRow(lines[i])) {
        rows.push(cells(lines[i]).map(parseInline))
        i += 1
      }
      blocks.push({ kind: 'table', head, rows })
      continue
    }
    if (isQuote(line)) {
      const parts: string[] = []
      while (i < lines.length && isQuote(lines[i])) {
        parts.push(lines[i].replace(/^\s*>\s?/, ''))
        i += 1
      }
      blocks.push({ kind: 'quote', children: parseInline(parts.join(' ').trim()) })
      continue
    }
    if (isBullet(line)) {
      const items: string[] = []
      while (i < lines.length) {
        const l = lines[i]
        if (isBullet(l)) {
          items.push(l.replace(/^\s*[-*]\s+/, ''))
        } else if (l.trim() && /^\s+/.test(l) && items.length) {
          items[items.length - 1] += ' ' + l.trim()
        } else if (!l.trim() && i + 1 < lines.length && isBullet(lines[i + 1])) {
          // blank line between items: same list
        } else {
          break
        }
        i += 1
      }
      blocks.push({ kind: 'list', items: items.map((t) => parseInline(t.trim())) })
      continue
    }
    const parts: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() &&
      !isHeading(lines[i]) &&
      !isBullet(lines[i]) &&
      !isQuote(lines[i]) &&
      !isRule(lines[i]) &&
      !isTableRow(lines[i])
    ) {
      parts.push(lines[i].trim())
      i += 1
    }
    if (parts.length) {
      blocks.push({ kind: 'paragraph', children: parseInline(parts.join(' ')) })
    } else {
      // A line no rule accepted (e.g. a lone table row): keep it as text.
      blocks.push({ kind: 'paragraph', children: parseInline(line.trim()) })
      i += 1
    }
  }
  return blocks
}

/** Plain text of a run of inlines (for tests and empty checks). */
export function inlineText(nodes: Inline[]): string {
  return nodes
    .map((n) => (n.kind === 'text' || n.kind === 'code' ? n.text : inlineText(n.children)))
    .join('')
}
