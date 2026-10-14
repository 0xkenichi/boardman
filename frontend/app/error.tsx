'use client'

/**
 * Root error boundary — catches render failures on the landing, /football/*,
 * /admin and anything else without its own boundary (/rematch/* has one).
 */

import { useEffect } from 'react'
import { BookNotice, bookButton, bookButtonGhost } from '@/components/rematch/BookNotice'

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <BookNotice
      role="alert"
      stamp="VOID · TRY AGAIN"
      title="The page tore"
      actions={
        <>
          <button type="button" onClick={() => reset()} style={bookButton}>
            Try again
          </button>
          <a href="/" style={bookButtonGhost}>
            Back to the book
          </a>
        </>
      }
    >
      <p style={{ margin: 0 }}>
        Something broke while drawing this page. No money moved because of it — stakes
        live in the escrow, not in your browser.
      </p>
      {error?.digest ? (
        <p style={{ margin: '0.7rem 0 0', fontFamily: 'ui-monospace, Menlo, monospace', fontSize: '0.7rem' }}>
          ref {error.digest}
        </p>
      ) : null}
      {process.env.NODE_ENV !== 'production' && error?.message ? (
        <pre style={{ marginTop: '0.8rem', fontSize: 11, color: '#b04a32', whiteSpace: 'pre-wrap' }}>
          {error.message}
        </pre>
      ) : null}
    </BookNotice>
  )
}
