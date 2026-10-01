'use client'

/**
 * BookShell — the page shell wearing the bookmaker's day-book.
 * Every Boardman page renders on paper (book.css) with the /v2
 * type stack: Big Shoulders display, Instrument Serif body,
 * Space Mono figures. No tab bar — the top bar carries navigation.
 */

import '@fontsource-variable/big-shoulders'
import '@fontsource/instrument-serif'
import '@fontsource/instrument-serif/400-italic.css'
import '@fontsource/space-mono'
import './book.css'

export function BookShell({
  children,
  title,
}: {
  children: React.ReactNode
  title?: string
}) {
  return (
    <div className="bm-book">
      <div className="rm-wrap">
        {title ? (
          <div className="bk-head">
            <p className="bk-eyebrow">BOARDMAN · THE BOOK</p>
            <h1>{title}</h1>
          </div>
        ) : null}
        {children}
      </div>
    </div>
  )
}
