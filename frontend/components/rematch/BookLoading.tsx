/**
 * Route-level loading slip (for loading.tsx files): a quiet line on the paper
 * while the next page is fetched, so navigation never shows a blank sheet.
 */

const MONO = "'Space Mono', ui-monospace, 'SF Mono', Menlo, monospace"

export function BookLoading({ label = 'Turning the page…' }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        minHeight: '50vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2rem 1rem',
        fontFamily: MONO,
        fontSize: '0.75rem',
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        color: '#8a8478',
      }}
    >
      {label}
    </div>
  )
}
