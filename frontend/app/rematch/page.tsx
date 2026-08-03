'use client'

/**
 * Public Rematch page — playingsidequest.fun/rematch
 * Player-facing only: what they need to play. No internal roadmap/grant talk.
 */
import { useState } from 'react'
import Image from 'next/image'
import Link from 'next/link'

const BOT = 'https://t.me/ClawStationOfficialBot'
const FAUCET = 'https://faucet.circle.com/'

export default function RematchPage() {
  const [activeTab, setActiveTab] = useState<'flow' | 'play' | 'wallet' | 'legal'>('flow')

  const tabs: Record<string, React.ReactNode> = {
    flow: (
      <div className="space-y-6">
        <h2 className="text-xl font-bold text-emerald-400">How it works</h2>
        <ol className="list-decimal list-inside space-y-3 text-gray-300 text-sm leading-relaxed">
          <li>
            Open the bot → <strong className="text-white">Get USDC</strong> → fund your Arc
            address
          </li>
          <li>
            <strong className="text-white">New challenge</strong> → friend Accepts → both{' '}
            <strong className="text-white">Lock</strong>
          </li>
          <li>HOME / AWAY → play on console → submit FT photo (e.g. 5-3)</li>
          <li>Winner is paid in USDC · both earn PLAY score</li>
        </ol>

        <div className="bg-gray-900/80 p-4 rounded-xl border border-gray-800">
          <pre className="text-sm text-gray-300 whitespace-pre-wrap">{`🎮 My match      → Lock · Side · Submit
⚔️ New challenge  → @tag · stake · game
💰 Wallet         → balance · withdraw
💧 Get USDC       → Circle faucet → Arc`}</pre>
        </div>
      </div>
    ),
    play: (
      <div className="space-y-4 text-sm text-gray-300">
        <h2 className="text-xl font-bold text-emerald-400">PLAY score</h2>
        <p>
          Points for competing on Rematch. <strong className="text-white">Not cash.</strong>
        </p>
        <table className="w-full text-sm">
          <tbody className="text-gray-300">
            {[
              ['Win', '+100'],
              ['Loss', '+40'],
              ['Draw', '+50'],
              ['No-show', '−50'],
              ['Tiers', 'Bronze → Diamond'],
            ].map(([k, v]) => (
              <tr key={k} className="border-b border-gray-800/80">
                <td className="py-2 pr-4 text-gray-400">{k}</td>
                <td className="py-2 text-emerald-400/90">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ),
    wallet: (
      <div className="space-y-5 text-gray-300 text-sm">
        <h2 className="text-xl font-bold text-emerald-400">Wallet</h2>
        <p>
          Rematch runs on <strong className="text-white">Arc</strong>. Gas is paid in USDC — you
          only need USDC.
        </p>
        <ul className="list-disc list-inside space-y-2">
          <li>
            <strong className="text-white">Get USDC</strong> — bot button →{' '}
            <a href={FAUCET} className="text-emerald-400 underline" target="_blank" rel="noreferrer">
              Circle faucet
            </a>{' '}
            → Arc → paste your address
          </li>
          <li>
            <strong className="text-white">Withdraw</strong> — Wallet → Withdraw
          </li>
        </ul>
      </div>
    ),
    legal: (
      <div className="space-y-4 text-sm text-gray-300 leading-relaxed">
        <h2 className="text-xl font-bold text-amber-400">Before you play</h2>
        <ul className="list-disc list-inside space-y-2 text-gray-400">
          <li>Skill matches with proof — play fair.</li>
          <li>Only stake what you can afford to lose.</li>
          <li>PLAY is a score, not money.</li>
          <li>You must be allowed to use this product where you live.</li>
        </ul>
        <p className="text-xs text-gray-600 pt-2">Rematch by sideQuest</p>
      </div>
    ),
  }

  return (
    <div className="bg-[#050508] text-white">
      <div className="max-w-3xl mx-auto px-4 py-10">
        <div className="flex items-center gap-4 mb-6">
          <Image
            src="/rematch-logo.jpg"
            alt="Rematch"
            width={72}
            height={72}
            className="rounded-2xl border border-emerald-500/20 shadow-lg shadow-emerald-900/20"
            priority
          />
          <div>
            <p className="text-[11px] uppercase tracking-[2px] text-emerald-500/80 font-semibold mb-1">
              by sideQuest
            </p>
            <h1 className="text-4xl sm:text-5xl font-black tracking-tight">
              <span className="text-emerald-400">Re</span>
              <span className="text-white">match</span>
            </h1>
          </div>
        </div>

        <p className="text-gray-400 text-lg mb-2 max-w-xl leading-relaxed">
          Lock in. Play. Settle. Run it back.
        </p>
        <p className="text-gray-500 text-sm mb-8 max-w-xl">
          1v1 skill matches — console, iMessage, or mobile. Stake, lock, send the final photo.
          Telegram or web.
        </p>

        <div className="flex flex-wrap gap-3 mb-10">
          <Link
            href="/rematch/app"
            className="inline-flex items-center gap-2 px-6 py-3.5 rounded-2xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-sm shadow-lg shadow-emerald-900/30"
          >
            Open web app
          </Link>
          <a
            href={BOT}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 px-6 py-3.5 rounded-2xl bg-gray-900 hover:bg-gray-800 border border-gray-700 text-white font-semibold text-sm"
          >
            Telegram bot
          </a>
          <a
            href={FAUCET}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 px-6 py-3.5 rounded-2xl bg-gray-900 hover:bg-gray-800 border border-gray-700 text-white font-semibold text-sm"
          >
            Get money (faucet)
          </a>
        </div>

        <div className="flex flex-wrap gap-2 mb-8">
          {(
            [
              ['flow', 'How it works'],
              ['play', 'PLAY score'],
              ['wallet', 'Wallet'],
              ['legal', 'Before you play'],
            ] as const
          ).map(([tab, label]) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 rounded-xl text-sm font-medium transition ${
                activeTab === tab
                  ? 'bg-emerald-600 text-white'
                  : 'bg-gray-900 text-gray-400 hover:bg-gray-800 border border-gray-800'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="rounded-2xl border border-gray-800 bg-gray-950/50 p-6 sm:p-8">
          {tabs[activeTab]}
        </div>

      </div>
    </div>
  )
}
