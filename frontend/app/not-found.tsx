import type { Metadata } from 'next'
import { BookNotice, bookButton, bookButtonGhost } from '@/components/rematch/BookNotice'

export const metadata: Metadata = {
  title: 'Not in the book',
  robots: { index: false, follow: true },
}

export default function NotFound() {
  return (
    <BookNotice
      stamp="404 · NO SUCH PAGE"
      title="Not in the book"
      actions={
        <>
          <a href="/" style={bookButton}>
            Back to the book
          </a>
          <a href="/arena" style={bookButtonGhost}>
            The chess table
          </a>
          <a href="/app" style={bookButtonGhost}>
            Play
          </a>
        </>
      }
    >
      <p style={{ margin: 0 }}>
        <em>I’ve checked every page of the ledger.</em> Nothing is written under that
        address — it may have moved, or it never existed.
      </p>
    </BookNotice>
  )
}
