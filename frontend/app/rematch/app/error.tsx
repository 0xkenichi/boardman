'use client'

/**
 * Catches client render failures under /rematch/app/*. Rendered on book paper.
 */
export default function RematchAppError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div
      style={{
        minHeight: '60vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1.5rem',
        color: '#201f1a',
        fontFamily: "'Space Mono', ui-monospace, Menlo, monospace",
      }}
    >
      <div style={{ maxWidth: 400, textAlign: 'center' }}>
        <h1 style={{ fontSize: '1.15rem', textTransform: 'uppercase' }}>Something went wrong</h1>
        <p style={{ color: '#57534a', fontSize: '0.9rem' }}>
          Try again, or open the Telegram bot.
        </p>
        <button
          type="button"
          onClick={() => reset()}
          style={{
            background: '#256b48',
            color: '#f2eee2',
            border: 'none',
            borderRadius: 2,
            padding: '0.7rem 1.1rem',
            fontWeight: 700,
            cursor: 'pointer',
            marginRight: 8,
          }}
        >
          Try again
        </button>
        <a
          href="/app"
          style={{
            color: '#256b48',
            fontWeight: 600,
            fontSize: '0.9rem',
          }}
        >
          Home
        </a>
      </div>
    </div>
  )
}
