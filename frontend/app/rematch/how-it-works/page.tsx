import type { Metadata } from 'next'
import Link from 'next/link'
import { BookShell } from '@/components/rematch/BookShell'

export const metadata: Metadata = {
  title: 'How it works',
  description:
    'Four easy steps: lock the stakes in escrow, play the game, show who won, get paid. Boardman holds the stakes so the two players don’t have to trust each other. Testnet only — test USDC.',
}

const STEPS = [
  {
    n: '1',
    tag: 'LOCK',
    title: 'Both players put money in a safe box',
    body: 'You and your friend each put in the same amount of game money — test USDC on Arc testnet for now. Each of you locks your stake into an escrow contract before you start playing: the challenger first, then the opponent. Once both are in, neither of you can take it back, so you don’t have to trust each other. You do trust Boardman to referee.',
  },
  {
    n: '2',
    tag: 'PLAY',
    title: 'You play your game, for real',
    body: 'FIFA on the couch, a phone game, a chess board, anything. Boardman does not care what you play and never watches your game. He just holds the box and waits.',
  },
  {
    n: '3',
    tag: 'PROVE',
    title: 'Show a picture of the final score',
    body: 'When the game is done, take a photo of the last screen and send it to Boardman. A helper reads the picture and checks who won. If two people say different things, Boardman asks a person to look.',
  },
  {
    n: '4',
    tag: 'PAID',
    title: 'The winner gets the money',
    body: 'When both reports agree — or the picture check is sure — Boardman tells the box to pay. The winner gets the pot, and the contract takes Boardman’s small fee in the same transaction. If you disagree, there is a short dispute window and a person decides first. The payout is a transaction anyone can look up on the Arc testnet explorer.',
  },
]

export default function HowItWorksPage() {
  return (
    <BookShell title="How it works">
      <div style={{ maxWidth: '40rem', margin: '0 auto', padding: '0 1rem 3.5rem' }}>
        <p className="bk-lede" style={{ margin: '0 0 2rem' }}>
          Boardman is like the grown-up at the table who holds everyone&apos;s
          money so the game stays fair. <em>Four steps. That&apos;s the whole
          thing.</em>
        </p>

        <div className="rm-stack-lg">
          {STEPS.map((s) => (
            <section key={s.n} className="rm-card">
              <p className="bk-step-n">{s.n}</p>
              <p className="rm-section-title">{s.tag}</p>
              <h2 className="bk-step-title">{s.title}</h2>
              <p className="rm-muted" style={{ margin: 0, lineHeight: 1.7 }}>
                {s.body}
              </p>
            </section>
          ))}
        </div>

        <div className="rm-card rm-card-hero" style={{ textAlign: 'center', marginTop: '1.75rem' }}>
          <h2 className="bk-step-title" style={{ marginBottom: '0.5rem' }}>
            Want to try it?
          </h2>
          <p className="rm-muted" style={{ margin: '0 0 1rem' }}>
            The money right now is practice money — it&apos;s free. You can&apos;t
            lose anything real.
          </p>
          <div className="rm-btn-row">
            <Link href="/app" className="rm-btn rm-btn-primary">
              Go play
            </Link>
            <Link href="/questions" className="rm-btn rm-btn-ghost">
              Questions? Read this first
            </Link>
          </div>
        </div>

        <div style={{ textAlign: 'center', marginTop: '1.75rem' }}>
          <span className="bk-stamp">FAIR · FAST · YOURS TO KEEP</span>
        </div>
      </div>
    </BookShell>
  )
}
