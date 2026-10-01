'use client'

/**
 * Catches client render failures on /rematch/* so users never see a blank crash.
 * Rendered on the book paper.
 */
export default function RematchError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div
      style={{
        minHeight: '100vh',
        background: '#f2eee2',
        color: '#201f1a',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1.5rem',
        fontFamily: "'Space Mono', ui-monospace, Menlo, monospace",
      }}
    >
      <div style={{ maxWidth: 420, textAlign: 'center' }}>
        <h1 style={{ fontSize: '1.25rem', marginBottom: '0.5rem', textTransform: 'uppercase' }}>
          Something went wrong
        </h1>
        <p style={{ color: '#57534a', fontSize: '0.9rem', marginBottom: '1.25rem' }}>
          The book hit a snag. Wallet-extension noise in the console is usually safe to
          ignore — this page is for real crashes.
        </p>
        <button
          type="button"
          onClick={() => reset()}
          style={{
            background: '#256b48',
            color: '#f2eee2',
            border: 'none',
            borderRadius: 2,
            padding: '0.75rem 1.25rem',
            fontWeight: 700,
            cursor: 'pointer',
            marginRight: 8,
          }}
        >
          Try again
        </button>
        <a
          href="/"
          style={{
            display: 'inline-block',
            background: 'transparent',
            color: '#201f1a',
            borderRadius: 2,
            padding: '0.75rem 1.25rem',
            fontWeight: 600,
            textDecoration: 'none',
            border: '1px solid rgba(32, 31, 26, 0.4)',
          }}
        >
          Back to the book
        </a>
        {process.env.NODE_ENV !== 'production' && error?.message ? (
          <pre
            style={{
              marginTop: '1.25rem',
              textAlign: 'left',
              fontSize: 11,
              color: '#b04a32',
              whiteSpace: 'pre-wrap',
            }}
          >
            {error.message}
          </pre>
        ) : null}
      </div>
    </div>
  )
}
