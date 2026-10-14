/**
 * BookNotice — a single slip on the cream day-book paper, for the pages that
 * sit outside any shell: not-found, error boundaries and loading states.
 * Self-contained (inline styles + the book fonts) so it renders the same
 * under the root layout, /football, /admin or /v2.
 */

import '@fontsource-variable/big-shoulders'
import '@fontsource/instrument-serif'
import '@fontsource/space-mono'

const INK = '#201f1a'
const MUTED = '#57534a'
const DIM = '#8a8478'
const GREEN = '#256b48'
const RED = '#b04a32'
const MONO = "'Space Mono', ui-monospace, 'SF Mono', Menlo, monospace"
const SERIF = "'Instrument Serif', Georgia, serif"
const DISPLAY = "'Big Shoulders Variable', 'Arial Narrow', sans-serif"

export const bookButton: React.CSSProperties = {
  display: 'inline-block',
  background: GREEN,
  color: '#f2eee2',
  border: 0,
  borderRadius: 2,
  padding: '0.7rem 1.15rem',
  fontFamily: MONO,
  fontSize: '0.75rem',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  textDecoration: 'none',
  cursor: 'pointer',
}

export const bookButtonGhost: React.CSSProperties = {
  ...bookButton,
  background: 'transparent',
  color: INK,
  border: '1px solid rgba(32, 31, 26, 0.4)',
}

export function BookNotice({
  stamp,
  title,
  children,
  actions,
  role,
}: {
  stamp: string
  title: string
  children?: React.ReactNode
  actions?: React.ReactNode
  role?: 'alert' | 'status'
}) {
  return (
    <div
      role={role}
      style={{
        minHeight: '70vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2.5rem 1rem',
        background: '#f2eee2',
        color: INK,
        fontFamily: SERIF,
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 440,
          border: '1px solid rgba(32, 31, 26, 0.4)',
          borderRadius: 3,
          background: '#f9f6ec',
          padding: '1.4rem 1.3rem 1.3rem',
          transform: 'rotate(-0.5deg)',
          boxShadow: '3px 4px 0 rgba(32, 31, 26, 0.14)',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            gap: '1rem',
            borderBottom: '1px dashed rgba(32, 31, 26, 0.4)',
            paddingBottom: '0.6rem',
            marginBottom: '1rem',
            fontFamily: MONO,
            fontSize: '0.7rem',
            letterSpacing: '0.14em',
            color: DIM,
          }}
        >
          <span>BOARDMAN · THE BOOK</span>
          <span style={{ color: RED }}>{stamp}</span>
        </div>
        <h1
          style={{
            fontFamily: DISPLAY,
            fontVariationSettings: "'wght' 640",
            fontSize: '2rem',
            lineHeight: 1,
            textTransform: 'uppercase',
            margin: '0 0 0.7rem',
          }}
        >
          {title}
        </h1>
        {children ? (
          <div style={{ color: MUTED, fontSize: '1.05rem', lineHeight: 1.5 }}>{children}</div>
        ) : null}
        {actions ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem', marginTop: '1.2rem' }}>
            {actions}
          </div>
        ) : null}
      </div>
    </div>
  )
}
