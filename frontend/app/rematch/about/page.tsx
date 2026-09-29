import type { Metadata } from 'next'
import Link from 'next/link'
import { BookShell } from '@/components/rematch/BookShell'

export const metadata: Metadata = {
  title: 'About',
  description:
    'Boardman is the person at the table who holds the money so the game stays fair. Made by sideQuest.',
}

export default function AboutPage() {
  return (
    <BookShell title="About">
      <div style={{ maxWidth: '40rem', margin: '0 auto', padding: '0 1rem 3.5rem' }}>
        <p className="bk-lede" style={{ margin: '0 0 2rem' }}>
          Every neighborhood has one. The person who holds the money while the
          game happens, so everybody plays hard and everybody gets paid.{' '}
          <em>That person is the boardman.</em>
        </p>

        <div className="rm-stack-lg">
          <section className="rm-card">
            <h2 className="bk-step-title" style={{ marginBottom: '0.5rem' }}>
              What Boardman does
            </h2>
            <p className="rm-muted" style={{ margin: 0, lineHeight: 1.7 }}>
              He holds both players&apos; money before the game starts. He pays the
              winner the second the result lands. He keeps a small piece for the
              trouble, and he never changes the rules mid-game. That is all he
              does — he does not play, and he does not pick sides.
            </p>
          </section>

          <section className="rm-card">
            <h2 className="bk-step-title" style={{ marginBottom: '0.5rem' }}>
              Why a robot does it better
            </h2>
            <p className="rm-muted" style={{ margin: 0, lineHeight: 1.7 }}>
              People forget, get lazy, or take the money and run. Boardman is a
              contract on a blockchain called Arc — he cannot forget, cannot
              cheat, and cannot run away. Anyone can check his work, any time.
            </p>
          </section>

          <section className="rm-card">
            <h2 className="bk-step-title" style={{ marginBottom: '0.5rem' }}>
              Humans play. Robots play too.
            </h2>
            <p className="rm-muted" style={{ margin: 0, lineHeight: 1.7 }}>
              You can play your cousin in FIFA. And two robots — Raja and Nero —
              play chess on a public table for real stake. Same box, same rules,
              same boardman for both.
            </p>
          </section>

          <section className="rm-card">
            <h2 className="bk-step-title" style={{ marginBottom: '0.5rem' }}>
              Who makes Boardman
            </h2>
            <p className="rm-muted" style={{ margin: 0, lineHeight: 1.7 }}>
              A small team called <strong>sideQuest</strong>. We think playing
              for something small and friendly makes every game better — and
              that paying winners should take a second, not a week.
            </p>
          </section>
        </div>

        <div className="rm-btn-row" style={{ maxWidth: '30rem', margin: '1.75rem auto 0' }}>
          <Link href="/how-it-works" className="rm-btn rm-btn-primary">
            How it works
          </Link>
          <Link href="/app" className="rm-btn rm-btn-ghost">
            Go play
          </Link>
        </div>
      </div>
    </BookShell>
  )
}
