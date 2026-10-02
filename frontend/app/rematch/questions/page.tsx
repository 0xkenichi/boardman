import type { Metadata } from 'next'
import Link from 'next/link'
import { BookShell } from '@/components/rematch/BookShell'

export const metadata: Metadata = {
  title: 'Questions',
  description:
    'Simple answers: What if my friend does not pay? Is the money real? How do I get game money? What games can I play?',
}

const QA = [
  {
    q: 'Is the money real?',
    a: 'Right now: no. Everything runs on practice money called testnet USDC. It is free from a tap, and you can never lose anything real. When real money turns on later, we will say it loudly on every page.',
  },
  {
    q: 'What if my friend does not pay me after losing?',
    a: 'That can’t happen. The money goes into the box before the game starts, both players together. Nobody can take it back, not even your friend. When you win, the box pays you by itself.',
  },
  {
    q: 'What if my friend never shows up?',
    a: 'Boardman notices and gives your money back by itself. You never have to chase anyone or ask for it.',
  },
  {
    q: 'Who checks who won?',
    a: 'You send a photo of the final screen. A helper reads it. If something looks wrong or two players disagree, a real person from the house looks at it and decides.',
  },
  {
    q: 'Can Boardman run away with the money?',
    a: 'No. The box is not a person — it is a contract living on a blockchain called Arc. It follows its rules exactly, and anyone can read those rules and check the money going in and out.',
  },
  {
    q: 'How do I get game money?',
    a: 'Go to the Wallet page, copy your address, and tap free practice money from the Circle faucet. It takes about a minute. The guide walks you through it.',
  },
  {
    q: 'What games can I play?',
    a: 'Anything you and your friend agree on — console games, phone games, PC games, even a board game on the kitchen table. Boardman settles the money; you play the game anywhere.',
  },
  {
    q: 'What are Raja and Nero?',
    a: 'Two robots that play chess against each other on a live public board, for real stake. You can watch them any time — and bet on which one wins while the window is open.',
  },
  {
    q: 'Do I need a crypto wallet or seed words?',
    a: 'No. Boardman gives you a play wallet when you open the Telegram bot once. No seed phrases, nothing to write down, nothing to lose.',
  },
  {
    q: 'How much does Boardman keep?',
    a: 'A small piece of each pot, written in the contract: half a dollar flat on tiny games, 7% on most games, 10% on very big ones. The exact fee always shows before you lock anything — you see what the house keeps before any money moves.',
  },
]

export default function QuestionsPage() {
  return (
    <BookShell title="Questions">
      <div style={{ maxWidth: '40rem', margin: '0 auto', padding: '0 1rem 3.5rem' }}>
        <p className="bk-lede" style={{ margin: '0 0 2rem' }}>
          The questions everyone asks, answered in plain words. Still stuck?{' '}
          <Link href="/contact">Write to the desk</Link> — a person reads it.
        </p>

        <div className="rm-stack-lg">
          {QA.map((item, i) => (
            <section key={i} className="rm-card">
              <h2 className="bk-q">{item.q}</h2>
              <p className="rm-muted" style={{ margin: 0, lineHeight: 1.7 }}>
                {item.a}
              </p>
            </section>
          ))}
        </div>

        <div className="rm-btn-row" style={{ maxWidth: '30rem', margin: '1.75rem auto 0' }}>
          <Link href="/how-it-works" className="rm-btn rm-btn-primary">
            See how it works
          </Link>
          <Link href="/app" className="rm-btn rm-btn-ghost">
            Go play
          </Link>
        </div>
      </div>
    </BookShell>
  )
}
