'use client'

import Link from 'next/link'
import { BookShell } from '@/components/rematch/BookShell'
import { REMATCH_BOT_URL } from '@/lib/rematchLinks'

const FAUCET = 'https://faucet.circle.com/'

export default function HowToPlayPage() {
  return (
    <BookShell title="How to play">
      <div className="rm-stack-lg">
        <div className="rm-card rm-card-hero">
          <p className="rm-section-title">The short version</p>
          <p className="rm-muted" style={{ margin: 0, lineHeight: 1.6 }}>
            One Telegram account, one Arc USDC play wallet, two ways on.{' '}
            <strong>Play a friend</strong> — lock USDC on a challenge, play the
            real game, winner gets paid before they leave the table. Or{' '}
            <strong>better — bet the arena</strong>: watch Raja vs Nero and ride
            the pari-mutuel pot. Same balance on Telegram and the website.
          </p>
        </div>

        <div className="rm-card rm-card-warn">
          <p className="rm-section-title">House rule №1 — testnet money only</p>
          <p className="rm-muted" style={{ margin: 0, lineHeight: 1.6 }}>
            Everything here runs on <strong>Arc testnet USDC</strong> from{' '}
            <a href={FAUCET} target="_blank" rel="noreferrer">faucet.circle.com</a> —
            free test money, not real cash. <strong>Don&apos;t send real USDC
            anywhere on Boardman yet</strong> — the whole book is testnet.
          </p>
        </div>

        <div className="rm-card">
          <p className="rm-section-title">0 · Fund the play wallet (once)</p>
          <ol className="rm-muted bk-rules" style={{ margin: 0, paddingLeft: '1.2rem', lineHeight: 1.75 }}>
            <li>
              Open the Telegram bot once with <code className="rm-code">/start</code> so
              the house opens your wallet.
            </li>
            <li>
              Open <Link href="/app/wallet">Wallet &amp; fund</Link> and copy your Arc USDC
              play address.
            </li>
            <li>
              Get Arc testnet USDC from{' '}
              <a href={FAUCET} target="_blank" rel="noreferrer">
                faucet.circle.com
              </a>{' '}
              and send it there — <strong>testnet only, don&apos;t send real money</strong>.
              Every stake and every bet comes off this one wallet.
            </li>
          </ol>
          <div className="rm-btn-row rm-mt-2" style={{ flexWrap: 'wrap' }}>
            <a href={FAUCET} target="_blank" rel="noreferrer" className="rm-btn rm-btn-primary">
              Open the faucet
            </a>
            <Link href="/app/wallet" className="rm-btn rm-btn-ghost">
              My wallet
            </Link>
            <a href={REMATCH_BOT_URL} target="_blank" rel="noreferrer" className="rm-btn rm-btn-ghost">
              Telegram bot
            </a>
          </div>
        </div>

        <div className="rm-card">
          <p className="rm-section-title">1 · Play a friend</p>
          <ol className="rm-muted bk-rules" style={{ margin: 0, paddingLeft: '1.2rem', lineHeight: 1.75 }}>
            <li>
              <strong>Call it.</strong> Tap{' '}
              <Link href="/app/challenge">Challenge a friend</Link>, enter their{' '}
              <code className="rm-code">@tag</code>, name the stake ($2–$25), the
              platform and the game. They must have opened the bot or app once.
            </li>
            <li>
              <strong>They accept.</strong> Your friend opens the match code in the bot
              or the app and takes the bet. Open challenges sit under{' '}
              <Link href="/app/match">My matches</Link>.
            </li>
            <li>
              <strong>Lock.</strong> Both players lock their stake — the money goes
              into escrow and the match goes live. Nobody can blink after that.
            </li>
            <li>
              <strong>Play.</strong> Play the real game wherever you two play it — the
              house settles money, not moves.
            </li>
            <li>
              <strong>Show the final screen.</strong> Upload the proof photo here or in
              the bot. The winner is paid straight to the same play wallet.
            </li>
          </ol>
          <div className="rm-btn-row rm-mt-2">
            <Link href="/app/challenge" className="rm-btn rm-btn-primary">
              Challenge a friend
            </Link>
            <Link href="/app/match" className="rm-btn rm-btn-ghost">
              My matches
            </Link>
          </div>
        </div>

        <div className="rm-card">
          <p className="rm-section-title">2 · Bet the arena (Raja vs Nero)</p>
          <ol className="rm-muted bk-rules" style={{ margin: 0, paddingLeft: '1.2rem', lineHeight: 1.75 }}>
            <li>
              <strong>Open the arena.</strong> Watch the two house agents play blitz
              chess — the house seats one of them on White, moves stream live.
            </li>
            <li>
              <strong>Sign in.</strong> Telegram login, same account and play wallet
              as the bot.
            </li>
            <li>
              <strong>Take a side.</strong> Pick <strong>Raja</strong>,{' '}
              <strong>Nero</strong>, or <strong>Draw</strong> and set an amount
              ($0.25–$50) while the window is open.
            </li>
            <li>
              <strong>Hold your ticket.</strong> The pot pays out after the{' '}
              house take — the odds shown are &ldquo;if you bet now, the pot pays
              about&hellip;&rdquo;. Your ticket updates live as the match plays.
            </li>
            <li>
              <strong>Get paid.</strong> Win and the pot pays your share. A draw is a
              real result: draw tickets win the whole pool, side bets on Raja or Nero
              lose. Same numbers on Telegram and the website.
            </li>
          </ol>
          <div className="rm-btn-row rm-mt-2">
            <a href="/arena" className="rm-btn rm-btn-primary">
              Open the arena
            </a>
            <Link href="/app/wallet" className="rm-btn rm-btn-ghost">
              Fund first
            </Link>
          </div>
        </div>

        <div className="rm-card">
          <p className="rm-section-title">The fine print</p>
          <ul className="rm-muted bk-rules" style={{ margin: 0, paddingLeft: '1.2rem', lineHeight: 1.75 }}>
            <li>One balance everywhere — Telegram, the app, and the arena use the same play wallet.</li>
            <li>Challenges lock real stakes into escrow; the winner is paid out, not credited twice.</li>
            <li>Right now everything runs on Arc testnet USDC from the Circle faucet — testnet only, don&apos;t send real money. The flows and numbers are the same as live.</li>
            <li>Don&apos;t see a match? The robots play around the clock — check the arena or Telegram for a fresh table.</li>
          </ul>
        </div>

        <div style={{ textAlign: 'center' }}>
          <span className="bk-stamp">SETTLED · ARC · &lt;1S</span>
        </div>
      </div>
    </BookShell>
  )
}
