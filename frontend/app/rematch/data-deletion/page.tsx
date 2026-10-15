import type { Metadata } from 'next'
import Link from 'next/link'
import { BookShell } from '@/components/rematch/BookShell'
import { BRAND } from '@/lib/brand'

export const metadata: Metadata = {
  title: 'Delete Your Data',
  description:
    'How to ask Boardman to delete your data from Telegram, WhatsApp or the web, what gets deleted, what the law makes us keep, and what no one can delete.',
  alternates: { canonical: 'https://boardman.playingsidequest.fun/data-deletion' },
}

export const dynamic = 'force-static'

const UPDATED = '15 October 2026'
const MAIL = BRAND.email
// There is no in-chat delete command yet (src/channels has STOP/START only),
// so deletion runs through the inbox. Add the command here when it ships.
const DELETE_MAILTO = `mailto:${MAIL}?subject=${encodeURIComponent('Delete my Boardman data')}`

export default function DataDeletionPage() {
  return (
    <BookShell title="Delete Your Data">
      <article className="bk-legal">
        <p className="bk-legal-meta">LAST UPDATED {UPDATED.toUpperCase()}</p>

        <p className="bk-lede" style={{ marginBottom: '1.4rem' }}>
          Want your page torn out of the book? Here is how, and what the house has to keep
          even then.
        </p>

        <h2>How to ask</h2>
        <div className="bk-legal-box">
          <p>
            Email <a href={DELETE_MAILTO}>{MAIL}</a> with the subject{' '}
            <strong>&ldquo;Delete my Boardman data&rdquo;</strong>. Tell us:
          </p>
          <ul>
            <li>your Boardman tag;</li>
            <li>
              the Telegram username or the WhatsApp number linked to your account, or send the
              email from the email address linked to it;
            </li>
            <li>an external wallet address for any balance you still hold (see below).</li>
          </ul>
        </div>
        <p>
          To make sure nobody deletes your account for you, we confirm the request in the chat
          linked to your account (Telegram or WhatsApp) or from that linked email before we act.
          We finish within <strong>30 days</strong> of confirming and write back when it is done.
        </p>
        <p>
          Only want the messages to stop? Send <strong>STOP</strong> to Boardman on WhatsApp, or
          block the bot on Telegram. That turns off notices without deleting anything.
        </p>

        <h2>Before we delete</h2>
        <ul>
          <li>
            <strong>Your money comes first.</strong> Any balance in your play wallet is sent to
            the external address you give us, after the usual security checks. We cannot
            delete an account that still holds funds.
          </li>
          <li>
            <strong>Open matches finish first.</strong> Locked stakes are settled or refunded,
            and open disputes are decided, before the account is closed.
          </li>
        </ul>

        <h2>What we delete</h2>
        <ul>
          <li>Your profile: tag, display name, bio, game ids, backup email and transaction-password hash.</li>
          <li>Your chat identities: Telegram id and username, WhatsApp number and profile name, and the links between them.</li>
          <li>Your chat history with the bot as we store it, notice preferences and opt-in records.</li>
          <li>Match screenshots and photos you sent as evidence.</li>
          <li>Contact-form and waitlist entries, and your web sessions.</li>
          <li>Your entries on the public leaderboard and challenge boards.</li>
        </ul>

        <h2>What we keep, and why</h2>
        <ul>
          <li>
            <strong>Transaction and ledger records</strong> (deposits, top-ups, stakes, payouts,
            refunds, sends, withdrawals, fees and their audit records). Financial, tax and
            anti-money-laundering law makes us keep them, generally for at least five years.
            We cut them loose from your name and contact details where we can, and delete them
            when the legal period ends.
          </li>
          <li>
            <strong>A minimal fraud record</strong> if your account was suspended for cheating or
            fraud, so the same person cannot simply sign up again.
          </li>
          <li>
            <strong>Records we need for a legal claim</strong> or that an authority has lawfully
            asked us to keep.
          </li>
        </ul>

        <h2>What no one can delete</h2>
        <ul>
          <li>
            <strong>Blockchain data.</strong> Your wallet addresses and every transaction on Arc,
            Avalanche or Stellar are public and permanent. Nobody, including us, can erase them.
            Once your account is closed we stop using your play wallet, but its history stays on
            chain.
          </li>
          <li>
            <strong>Your copy of the chat.</strong> Messages in your Telegram or WhatsApp app are
            stored by those apps. Delete the chat there, and see Telegram&apos;s and Meta&apos;s
            own policies for what they keep.
          </li>
        </ul>

        <p>
          The full picture of what we collect and why is in the{' '}
          <Link href="/privacy">Privacy Policy</Link>.
        </p>
      </article>
    </BookShell>
  )
}
