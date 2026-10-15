import type { ReactNode } from 'react'
import type { Block, Inline } from '@/lib/legalMarkdown'

/**
 * Renders the blocks from lib/legalMarkdown as React elements. Every string
 * goes in as a text child, so React escapes it; no raw HTML is ever injected.
 * Styles: .bk-legal in book.css.
 */

function renderInline(nodes: Inline[]): ReactNode[] {
  return nodes.map((n, i) => {
    switch (n.kind) {
      case 'text':
        return n.text
      case 'code':
        return <code key={i}>{n.text}</code>
      case 'strong':
        return <strong key={i}>{renderInline(n.children)}</strong>
      case 'em':
        return <em key={i}>{renderInline(n.children)}</em>
      case 'link':
        return n.href.startsWith('https://boardman.playingsidequest.fun/') || n.href.startsWith('/') ? (
          <a key={i} href={n.href.replace('https://boardman.playingsidequest.fun', '')}>
            {renderInline(n.children)}
          </a>
        ) : (
          <a key={i} href={n.href} target="_blank" rel="noreferrer">
            {renderInline(n.children)}
          </a>
        )
    }
  })
}

export function LegalMarkdown({ blocks }: { blocks: Block[] }) {
  return (
    <>
      {blocks.map((b, i) => {
        switch (b.kind) {
          case 'heading':
            return b.level <= 2 ? (
              <h2 key={i}>{renderInline(b.children)}</h2>
            ) : (
              <h3 key={i}>{renderInline(b.children)}</h3>
            )
          case 'paragraph':
            return <p key={i}>{renderInline(b.children)}</p>
          case 'quote':
            return <blockquote key={i}>{renderInline(b.children)}</blockquote>
          case 'rule':
            return <hr key={i} />
          case 'list':
            return (
              <ul key={i}>
                {b.items.map((item, j) => (
                  <li key={j}>{renderInline(item)}</li>
                ))}
              </ul>
            )
          case 'table':
            return (
              <div key={i} className="bk-legal-table">
                <table>
                  <thead>
                    <tr>
                      {b.head.map((c, j) => (
                        <th key={j}>{renderInline(c)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {b.rows.map((r, j) => (
                      <tr key={j}>
                        {r.map((c, k) => (
                          <td key={k}>{renderInline(c)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
        }
      })}
    </>
  )
}
