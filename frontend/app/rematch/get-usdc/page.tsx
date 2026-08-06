'use client'

/**
 * Fund helper — shows the player's Arc address + Circle faucet.
 * Bot deep-links here with ?address=0x… so users don't hunt for their wallet.
 * Circle's public faucet requires human reCAPTCHA; we cannot auto-submit for them.
 */
import { Suspense, useMemo, useState } from 'react'
import Image from 'next/image'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'

const BOT = 'https://t.me/ClawStationOfficialBot'
const FAUCET = 'https://faucet.circle.com/'

function FundInner() {
  const params = useSearchParams()
  const address = (params.get('address') || '').trim()
  const [copied, setCopied] = useState(false)

  const isAddr = useMemo(
    () => /^0x[a-fA-F0-9]{40}$/.test(address),
    [address]
  )

  async function copy() {
    if (!isAddr) return
    try {
      await navigator.clipboard.writeText(address)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="bg-[#050508] text-white">
      <div className="max-w-lg mx-auto px-4 py-10 space-y-6">
        <div className="flex items-center gap-3">
          <Image
            src="/boardman-logo.jpg"
            alt="Boardman"
            width={48}
            height={48}
            className="rounded-xl border border-emerald-500/20"
          />
          <div>
            <p className="text-[11px] uppercase tracking-[2px] text-emerald-500/80 font-semibold">
              Arc · Get USDC
            </p>
            <h1 className="text-2xl font-black tracking-tight">Fund your wallet</h1>
          </div>
        </div>

        {isAddr ? (
          <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-4 space-y-3">
            <p className="text-xs text-gray-400 uppercase tracking-wide">Your Arc address</p>
            <code className="block text-sm text-emerald-300 break-all select-all">{address}</code>
            <button
              type="button"
              onClick={copy}
              className="w-full py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 font-semibold text-sm"
            >
              {copied ? 'Copied ✓' : 'Copy address'}
            </button>
          </div>
        ) : (
          <div className="rounded-2xl border border-gray-800 bg-gray-950/50 p-4 text-sm text-gray-400">
            Open <strong className="text-white">Get USDC</strong> in the Telegram bot to load your
            address here automatically.
          </div>
        )}

        <ol className="list-decimal list-inside space-y-2 text-sm text-gray-300 leading-relaxed">
          <li>Copy your address above</li>
          <li>
            Open the faucet → choose <strong className="text-white">Arc Testnet</strong> →{' '}
            <strong className="text-white">USDC</strong>
          </li>
          <li>Paste address → request tokens</li>
          <li>Back in Telegram → Wallet → Refresh</li>
        </ol>

        <a
          href={FAUCET}
          target="_blank"
          rel="noreferrer"
          className="flex items-center justify-center w-full py-3.5 rounded-2xl bg-white text-black font-bold text-sm hover:bg-gray-100"
        >
          Open Circle faucet →
        </a>

        <p className="text-xs text-gray-600 text-center">
          Limit is set by Circle (often once per address every few hours).
        </p>
      </div>
    </div>
  )
}

export default function GetUsdcPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#050508] text-gray-500 flex items-center justify-center text-sm">
          Loading…
        </div>
      }
    >
      <FundInner />
    </Suspense>
  )
}
