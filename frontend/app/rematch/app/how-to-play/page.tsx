'use client'

import Link from 'next/link'
import { AppShell } from '@/components/AppShell'
import { REMATCH_BOT_URL } from '@/lib/rematchLinks'

const FAUCET = 'https://faucet.circle.com/'

export default function HowToPlayPage() {
  return (
    <AppShell title="How to play">
      <div className="rm-stack-lg">
        <div className="rm-card rm-card-hero">
          <p className="rm-section-title">The short version</p>
          <p className="rm-muted" style={{ margin: 0, lineHeight: 1.6 }}>
            One Telegram account, one Arc USDC play wallet, two ways to play.{' '}
            <strong>Play a friend</strong> — lock USDC on a challenge, play the real
            game, winner gets paid. Or <strong>bet the arena</strong> — watch Raja vs
            Nero and ride the pari-mutuel pot. Same balance on Telegram and the website.
          </p>
        </div>

        <div className="rm-card rm-card-warn">
          <p className="rm-section-title">🧪 Testnet money only — don&apos;t send real cash</p>
          <p className="rm-muted" style={{ margin: 0, lineHeight: 1.6 }}>
            Everything here runs on <strong>Arc testnet USDC</strong> from{' '}
            <a href={FAUCET} target="_blank" rel="noreferrer">faucet.circle.com</a> — it&apos;s
            free test money, not real cash. <strong>Don&apos;t send real USDC anywhere on Boardman
            yet</strong> — it&apos;s all testnet.
          </p>
        </div>

        <div className="rm-card">
          <p className="rm-section-title">0 · Fund your play wallet (once)</p>
          <ol className="rm-muted" style={{ margin: 0, paddingLeft: '1.1rem', lineHeight: 1.75 }}>
            <li>
              Open the Telegram bot once with <code className="rm-code">/start</code> so we
              create your wallet.
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
              and send it to that address — <strong>testnet only, don&apos;t send real money</strong>.
              This is the same wallet every stake and bet comes from.
            </li>
          </ol>
          <div className="rm-btn-row rm-mt-2">
            <a href={FAUCET} target="_blank" rel="noreferrer" className="rm-btn rm-btn-primary">
              🚰 Open faucet (testnet)
            </a>
            <Link href="/app/wallet" className="rm-btn rm-btn-ghost">
              💰 My wallet
            </Link>
            <a href={REMATCH_BOT_URL} target="_blank" rel="noreferrer" className="rm-btn rm-btn-ghost">
              Open Telegram bot
            </a>
          </div>
        </div>

        <div className="rm-card">
          <p className="rm-section-title">1 · Play a friend</p>
          <ol className="rm-muted" style={{ margin: 0, paddingLeft: '1.1rem', lineHeight: 1.75 }}>
            <li>
              <strong>Challenge.</strong> Tap{' '}
              <Link href="/app/challenge">Challenge a friend</Link>, enter their{' '}
              <code className="rm-code">@tag</code>, pick a stake ($1–$25), platform, and game.
              They must have opened the bot or app once.
            </li>
            <li>
              <strong>Accept.</strong> Your friend opens the match code in the bot or the app
              and accepts. An open challenge is findable under{' '}
              <Link href="/app/match">My matches</Link>.
            </li>
            <li>
              <strong>Lock.</strong> Both players lock their stake — the money goes into escrow
              and the match becomes live.
            </li>
            <li>
              <strong>Play.</strong> Play the real game wherever you two play it — the bot
              settles money, not moves.
            </li>
            <li>
              <strong>Submit proof.</strong> Upload the final screen photo here or in the bot.
              The winner is paid straight to the same play wallet.
            </li>
          </ol>
          <div className="rm-btn-row rm-mt-2">
            <Link href="/app/challenge" className="rm-btn rm-btn-primary">
              ⚔️ Challenge a friend
            </Link>
            <Link href="/app/match" className="rm-btn rm-btn-ghost">
              🎮 My matches
            </Link>
          </div>
        </div>

        <div className="rm-card">
          <p className="rm-section-title">2 · Bet the arena (Raja vs Nero)</p>
          <ol className="rm-muted" style={{ margin: 0, paddingLeft: '1.1rem', lineHeight: 1.75 }}>
            <li>
              <strong>Open the arena.</strong> Watch the two house agents play blitz chess —
              a coin flip picks White, moves stream live.
            </li>
            <li>
              <strong>Sign in.</strong> Telegram login, same account and play wallet as the bot.
            </li>
            <li>
              <strong>Bet.</strong> Pick <strong>Raja</strong>, <strong>Nero</strong>, or{' '}
              <strong>Draw</strong> and set an amount ($0.25–$50) while the window is open.
            </li>
            <li>
              <strong>Watch your ticket.</strong> The pot is pari-mutuel after a 5% take — the
              odds shown are &ldquo;if you bet now, the pot pays about&hellip;&rdquo;. Your ticket
              updates live as the match plays.
            </li>
            <li>
              <strong>Get paid.</strong> Win and the pot pays your share. Draw means a full
              refund. Same numbers on Telegram and the website.
            </li>
          </ol>
          <div className="rm-btn-row rm-mt-2">
            <a href="/agentic/arena.html" className="rm-btn rm-btn-primary">
              ♟️ Open the arena
            </a>
            <Link href="/app/wallet" className="rm-btn rm-btn-ghost">
              💰 Fund first
            </Link>
          </div>
        </div>

        <div className="rm-card">
          <p className="rm-section-title">Good to know</p>
          <ul className="rm-muted" style={{ margin: 0, paddingLeft: '1.1rem', lineHeight: 1.75 }}>
            <li>One balance everywhere — Telegram, the app, and the arena use the same play wallet.</li>
            <li>Challenges lock real stakes into escrow; the winner is paid out, not credited twice.</li>
            <li>Right now everything runs on Arc testnet USDC from the Circle faucet — testnet only, don&apos;t send real money. The flows and numbers are the same as live.</li>
            <li>Don&apos;t see a match? Hit <strong>Play next</strong> in the arena or check Telegram for a fresh table.</li>
          </ul>
        </div>
      </div>
    </AppShell>
  )
}
