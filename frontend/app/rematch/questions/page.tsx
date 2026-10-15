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
    a: 'That can’t happen. Both stakes go into the escrow box before the game starts — the challenger’s first, then the opponent’s — and your friend can’t take theirs back. When the result stands, Boardman tells the box to pay the winner.',
  },
  {
    q: 'What if my friend never shows up?',
    a: 'If they never lock their stake, Boardman’s sweep gives your stake back automatically. If nobody reports a result, both stakes go back after 24 hours. You never have to chase anyone for it.',
  },
  {
    q: 'Who checks who won?',
    a: 'You send a photo of the final screen. A helper reads it. If something looks wrong or two players disagree, a real person from the house looks at it and decides.',
  },
  {
    q: 'Can Boardman run away with the money?',
    a: 'While you play, the stakes sit in a contract on a blockchain called Arc, and anyone can check the money going in and out. But Boardman is not hands-off: your play wallet is run by Boardman through Circle, and Boardman decides when the box pays out. So you are trusting the house — one more reason everything is test money today.',
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
    q: 'Who are Raja, Nero and Sheila?',
    a: 'Three house agents — chess engines with their own styles — that take turns playing each other on a public board, for test USDC. You can watch them any time, and bet test USDC on who wins while the betting window is open.',
  },
  {
    q: 'Do I need a crypto wallet or seed words?',
    a: 'No. Boardman gives you a play wallet when you open the Telegram bot once. No seed phrases, nothing to write down, nothing to lose.',
  },
  {
    q: 'How much does Boardman keep?',
    a: 'A small piece of each pot, written in the contract and set by each player’s stake: half a dollar flat per player under $5, 7% from $5 to $500, 10% above that. The exact fee always shows before you lock anything — you see what the house keeps before any money moves.',
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
