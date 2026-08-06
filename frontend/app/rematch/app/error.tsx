'use client'

/**
 * Catches client render failures under /rematch/app/*
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
        color: '#fff',
        fontFamily: 'system-ui, sans-serif',
      }}
    >
      <div style={{ maxWidth: 400, textAlign: 'center' }}>
        <h1 style={{ fontSize: '1.15rem' }}>Something went wrong</h1>
        <p style={{ color: '#9ca3af', fontSize: '0.9rem' }}>
          Try again, or open the Telegram bot.
        </p>
        <button
          type="button"
          onClick={() => reset()}
          style={{
            background: '#059669',
            color: '#fff',
            border: 'none',
            borderRadius: 12,
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
            color: '#34d399',
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
