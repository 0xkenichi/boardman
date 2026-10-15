import type { Metadata } from 'next'
import Link from 'next/link'
import { BookShell } from '@/components/rematch/BookShell'
import { BRAND } from '@/lib/brand'
import { OPERATOR_PLACEHOLDER } from '@/lib/legalTerms'

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description:
    'What Boardman records when you play on Telegram, WhatsApp or the web, why, who processes it, how long it is kept, and how to see, fix or delete it.',
  alternates: { canonical: 'https://boardman.playingsidequest.fun/privacy' },
}

export const dynamic = 'force-static'

const UPDATED = '15 October 2026'
const MAIL = BRAND.email

/*
 * Drafted by engineering from the product as built (docs/LEGAL.md,
 * COMPLIANCE.md, docs/channels/CHANNELS_DESIGN.md). Open counsel points,
 * kept out of the public text and tracked here:
 *   [COUNSEL: legal entity name, company number, registered address]
 *   [COUNSEL: lawful bases per market (NDPA 2023 for Nigeria, GDPR-style elsewhere)]
 *   [COUNSEL: statutory retention period for transaction and AML records]
 *   [COUNSEL: transfer safeguards per processor]
 *   [COUNSEL: KYC and sanctions-screening data once that programme exists]
 */

const PROCESSORS: Array<[string, string]> = [
  ['Supabase', 'Database and private file storage for profiles, ledgers, chat identities and match evidence.'],
  ['Circle', 'Creates and operates the developer-controlled USDC play wallets and signs their transactions on our instruction.'],
  ['Paystack', 'Collects Naira top-ups. Card and bank details go to Paystack, not to us; we receive the payment reference, amount, status and email.'],
  ['Telegram', 'Carries your conversation with the Boardman bot and the Telegram login on the website.'],
  ['Meta (WhatsApp Business Platform)', 'Carries your conversation with Boardman on WhatsApp, including photos you send us.'],
  ['Vercel', 'Hosts the website and its server routes; sees your IP address and approximate country on each request.'],
  ['Cloudflare', 'Network edge, DNS and protection against abuse; sees your IP address and approximate country.'],
  ['Oracle Cloud', 'Hosts the Boardman API, the bots and their scheduled jobs.'],
  ['AI model providers (OpenAI, Google Gemini, Anthropic, OpenRouter)', 'Read match screenshots to check reported scores, help flag abuse, and power the AI agents. They receive the image or match data needed for the task, not your contact details.'],
]

export default function PrivacyPage() {
  return (
    <BookShell title="Privacy Policy">
      <article className="bk-legal">
        <p className="bk-legal-meta">LAST UPDATED {UPDATED.toUpperCase()}</p>

        <p className="bk-lede" style={{ marginBottom: '1.4rem' }}>
          The house keeps a book. This page says what goes in it, why, who else
          gets to read it, and how you get your page back out.
        </p>

        <div className="bk-legal-box">
          <p>
            <strong>Who we are.</strong> Boardman is run by {OPERATOR_PLACEHOLDER}. We are
            responsible for the personal data described here. Questions, requests and
            complaints: <a href={`mailto:${MAIL}`}>{MAIL}</a>.
          </p>
          <p>
            This policy covers the website at boardman.playingsidequest.fun, the Boardman
            bot on Telegram, Boardman on WhatsApp, and the Boardman Stack API. Read it with
            the <Link href="/terms">Terms of Service</Link>.
          </p>
        </div>

        <h2>1. What we collect</h2>

        <h3>When you talk to Boardman in a chat app</h3>
        <ul>
          <li>
            <strong>Telegram:</strong> your Telegram user id, username, display name and the
            chat id we reply to. Telegram does not give us your phone number.
          </li>
          <li>
            <strong>WhatsApp:</strong> your WhatsApp phone number, your WhatsApp profile name,
            and the user id Meta sends with your messages. We derive a country from the
            phone number&apos;s calling code.
          </li>
          <li>
            The messages, button taps and photos you send the bot, the replies we send, and
            when you last wrote to us (WhatsApp only lets us message you freely for 24 hours
            after you write).
          </li>
          <li>
            Whether you agreed to receive match and wallet notices, and when you sent STOP or
            START.
          </li>
          <li>Which chat accounts you linked to one Boardman profile, and the one-time codes used to link them.</li>
        </ul>

        <h3>Your Boardman profile</h3>
        <ul>
          <li>
            Your Boardman tag, display name and short bio; game ids you add (for example
            PlayStation or Xbox ids); a backup email if you give one.
          </li>
          <li>
            Your record: wins, losses, draws, streaks, reputation and tier. Your tag and record
            appear on the public leaderboard and on public challenges.
          </li>
          <li>
            A transaction password if you set one. We store only a hash of it, never the
            password itself.
          </li>
        </ul>

        <h3>Wallets and money</h3>
        <ul>
          <li>
            <strong>Your play wallet.</strong> We create a USDC wallet for you through Circle&apos;s
            developer-controlled wallet service. We keep its wallet id and address, and we hold
            its keys on your behalf, so in substance we look after the funds in it.
          </li>
          <li>
            External wallet addresses you sign in with, deposit from, withdraw to, or fund
            through on Arc, Avalanche or Stellar.
          </li>
          <li>
            Your transaction history and our ledger: deposits, top-ups, stakes locked, payouts,
            refunds, spectator tickets, marketplace purchases, sends, withdrawals, fees, the
            on-chain transaction hashes, and our audit records of each credit and debit.
          </li>
          <li>
            For Naira top-ups: the Paystack reference, amount, status and the email used, or
            the bank-transfer proof you upload. We never see your card number.
          </li>
        </ul>

        <h3>Matches and evidence</h3>
        <ul>
          <li>Challenges you create or accept, the game, your opponent, stakes, scores you report and the in-game names you give.</li>
          <li>
            Screenshots or photos of results, which we read with automated and AI checks.
            Photos sent on WhatsApp are copied into our private storage with their photo
            metadata removed; for photos sent on Telegram we keep Telegram&apos;s reference to
            the file.
          </li>
          <li>Dispute notes and the decisions our reviewers make.</li>
        </ul>

        <h3>On the website</h3>
        <ul>
          <li>
            Your IP address, read by our hosting edge to work out your country. We use the
            country to keep Boardman closed in restricted places; our geo-fence logs keep the
            country, not the IP address.
          </li>
          <li>Ordinary server logs: time, page or API route, browser type and errors.</li>
          <li>The details Telegram&apos;s login button shares when you sign in with it (id, name, username).</li>
          <li>Anything you type into the contact or waitlist form, such as your email and note.</li>
        </ul>

        <h3>Builders</h3>
        <p>
          If you build on the Stack API we keep your API key record, webhook URL, your
          agents, and the moves and results of every match they play.
        </p>

        <h3>What we do not collect</h3>
        <p>
          We do not run advertising or third-party analytics trackers, and we do not sell or
          rent personal data. We do not ask for identity documents today; if we start
          verifying identity for larger amounts we will update this page first.
        </p>

        <h2>2. Cookies and storage on your device</h2>
        <ul>
          <li>
            <strong>
              <code>rematch_session</code>
            </strong>{' '}
            keeps you signed in. It is signed, HttpOnly, lasts 7 days from your last visit,
            and expires after 30 days at most.
          </li>
          <li>
            <strong>
              <code>rematch_wallet_nonce</code>
            </strong>{' '}
            protects wallet sign-in. It lasts 10 minutes.
          </li>
          <li>
            Your browser&apos;s local storage remembers small things like a dismissed
            &ldquo;add to home screen&rdquo; notice or a spectator ticket you are watching.
          </li>
        </ul>
        <p>These are all strictly necessary for the service. There are no advertising cookies.</p>

        <h2>3. Why we use it</h2>
        <ul>
          <li>
            <strong>To run the table:</strong> open your account and wallet, take your stake,
            settle matches, pay winners, process top-ups and withdrawals, and talk to you in
            the chat you chose. This is needed to perform our agreement with you.
          </li>
          <li>
            <strong>To keep games fair and money safe:</strong> check results, resolve
            disputes, stop fraud, collusion and multiple accounts, and secure our systems.
            This is our legitimate interest, and yours.
          </li>
          <li>
            <strong>To follow the law:</strong> keep Boardman closed in restricted countries,
            keep financial and anti-money-laundering records, answer lawful requests and meet
            tax duties.
          </li>
          <li>
            <strong>To send notices you agreed to:</strong> match and wallet updates on
            WhatsApp or Telegram. Send STOP on WhatsApp, or block the Telegram bot, to turn
            them off. We do not send marketing messages without separate consent.
          </li>
          <li>
            <strong>To improve Boardman:</strong> fix bugs and understand which features get
            used, from our own logs.
          </li>
        </ul>

        <h2>4. Who else sees it</h2>
        <p>
          We share personal data only with the service providers that run Boardman for us,
          under contracts that limit what they may do with it:
        </p>
        <div className="bk-legal-table">
          <table>
            <thead>
              <tr>
                <th>Provider</th>
                <th>What they do for us</th>
              </tr>
            </thead>
            <tbody>
              {PROCESSORS.map(([name, role]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>{role}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>We also share data:</p>
        <ul>
          <li>with your opponent, as far as a match needs it (your tag, the score you reported and, in a dispute, the evidence);</li>
          <li>with the public, through the leaderboard, public challenges and the arena;</li>
          <li>with authorities, courts or advisers when the law requires it or to protect users and the platform;</li>
          <li>with a buyer or successor if the business changes hands, under this policy.</li>
        </ul>
        <p>
          <strong>Blockchains are public.</strong> Wallet addresses, amounts and transactions on
          Arc, Avalanche and Stellar are visible to anyone, forever. Telegram and Meta also
          handle your messages under their own privacy policies.
        </p>

        <h2>5. How long we keep it</h2>
        <ul>
          <li>
            <strong>Account, profile and chat identities:</strong> while your account is open.
            When you close it or ask us to delete it, we delete them within 30 days.
          </li>
          <li>
            <strong>Transaction, ledger and audit records:</strong> for as long as financial,
            tax and anti-money-laundering law requires, generally at least five years after the
            transaction or after your account closes.
          </li>
          <li>
            <strong>Match evidence:</strong> while the match can be disputed or reviewed for
            fraud, and no longer than 12 months after the match.
          </li>
          <li>
            <strong>Server logs:</strong> up to 90 days, unless we need them for a security
            investigation.
          </li>
          <li>
            <strong>Contact and waitlist messages:</strong> until we have answered and no
            longer than 24 months.
          </li>
        </ul>
        <p>
          See <Link href="/data-deletion">how to delete your data</Link> for what a deletion
          removes and what it cannot.
        </p>

        <h2>6. Your rights</h2>
        <p>Depending on where you live, you can ask us to:</p>
        <ul>
          <li>give you a copy of your personal data, in a portable format where that applies;</li>
          <li>correct data that is wrong;</li>
          <li>delete your data, subject to the records the law makes us keep;</li>
          <li>restrict or object to how we use it, including any profiling for fraud checks;</li>
          <li>withdraw consent you gave, such as for WhatsApp notices, at any time.</li>
        </ul>
        <p>
          Write to <a href={`mailto:${MAIL}`}>{MAIL}</a> from the email linked to your account,
          or tell us the Telegram username or WhatsApp number on it so we can confirm it is you
          in that chat. We answer within 30 days. You can also complain to your data protection
          authority; in Nigeria that is the Nigeria Data Protection Commission.
        </p>

        <h2>7. International transfers</h2>
        <p>
          Our providers run servers in several countries, including the United States and the
          European Union, so your data may be processed outside the country you live in. Where
          the law requires it, we rely on safeguards such as standard contractual clauses or
          the provider&apos;s own approved transfer mechanisms.
        </p>

        <h2>8. Security</h2>
        <p>
          Wallet keys sit with Circle under our controlled access, never in chat or on your
          phone. Sessions are signed and HttpOnly, data travels over encrypted connections,
          match evidence is never public, and staff access is limited to people who need
          it. No system is perfectly secure; if
          a breach puts your data at risk, we will tell you and the authorities as the law
          requires.
        </p>

        <h2>9. Over 18s only</h2>
        <p>
          Boardman is for adults: at least 18, or the age of majority where you live if
          higher. We do not knowingly collect data from children. If you think a child has an
          account, tell us and we will close it and delete the data.
        </p>

        <h2>10. Changes</h2>
        <p>
          We will post any change here and update the date at the top. If a change is
          significant, we will also tell you in the bot or on the site before it applies.
        </p>

        <h2>11. Contact</h2>
        <p>
          {OPERATOR_PLACEHOLDER}. Email <a href={`mailto:${MAIL}`}>{MAIL}</a>. Postal address
          available on request.
        </p>
      </article>
    </BookShell>
  )
}
