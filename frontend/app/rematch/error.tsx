'use client'

/**
 * Catches client render failures on /rematch/* so users never see a blank crash.
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
        background: '#050508',
        color: '#fff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1.5rem',
        fontFamily: 'system-ui, sans-serif',
      }}
    >
      <div style={{ maxWidth: 420, textAlign: 'center' }}>
        <h1 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>
          Something went wrong
        </h1>
        <p style={{ color: '#9ca3af', fontSize: '0.9rem', marginBottom: '1.25rem' }}>
          Boardman hit a client error. Wallet-extension noise in the console is usually
          safe to ignore — this box is for real app crashes.
        </p>
        <button
          type="button"
          onClick={() => reset()}
          style={{
            background: '#059669',
            color: '#fff',
            border: 'none',
            borderRadius: 12,
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
            background: '#111827',
            color: '#e5e7eb',
            borderRadius: 12,
            padding: '0.75rem 1.25rem',
            fontWeight: 600,
            textDecoration: 'none',
            border: '1px solid #1f2937',
          }}
        >
          Back to Boardman
        </a>
        {process.env.NODE_ENV !== 'production' && error?.message ? (
          <pre
            style={{
              marginTop: '1.25rem',
              textAlign: 'left',
              fontSize: 11,
              color: '#f87171',
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
