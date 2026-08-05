'use client'

import { useCallback, useEffect, useState } from 'react'

const MANIFEST_HREF = '/rematch/manifest.webmanifest'
const SW_PATH = '/rematch/sw.js'
const DISMISS_KEY = 'rm_a2hs_dismissed_v1'

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

/**
 * Rematch-only PWA bootstrap:
 * - Points the page at the Rematch manifest (not sideQuest)
 * - Registers /rematch/sw.js (scoped to /rematch/)
 * - Optional install banner when browser fires beforeinstallprompt
 */
export function RematchPwa() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null)
  const [show, setShow] = useState(false)
  const [isIos, setIsIos] = useState(false)
  const [standalone, setStandalone] = useState(false)

  useEffect(() => {
    // Prefer Rematch manifest over root sideQuest one
    let link = document.querySelector<HTMLLinkElement>('link[rel="manifest"][data-rematch]')
    if (!link) {
      link = document.createElement('link')
      link.rel = 'manifest'
      link.setAttribute('data-rematch', '1')
      document.head.appendChild(link)
    }
    link.href = MANIFEST_HREF

    // Soft-disable competing root manifest while on Rematch
    document.querySelectorAll<HTMLLinkElement>('link[rel="manifest"]:not([data-rematch])').forEach((el) => {
      el.setAttribute('data-rm-disabled', el.href)
      el.remove()
    })

    const ios =
      /iPad|iPhone|iPod/.test(navigator.userAgent) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
    setIsIos(ios)

    const isStandalone =
      window.matchMedia('(display-mode: standalone)').matches ||
      // @ts-expect-error iOS Safari
      Boolean(navigator.standalone)
    setStandalone(isStandalone)

    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register(SW_PATH, { scope: '/rematch/' }).catch(() => {
        /* ignore — install still works on many browsers without SW */
      })
    }

    const onBip = (e: Event) => {
      e.preventDefault()
      setDeferred(e as BeforeInstallPromptEvent)
      if (!sessionStorage.getItem(DISMISS_KEY) && !localStorage.getItem(DISMISS_KEY)) {
        setShow(true)
      }
    }
    window.addEventListener('beforeinstallprompt', onBip)

    // iOS: show tip once if not already installed
    if (ios && !isStandalone && !localStorage.getItem(DISMISS_KEY)) {
      setShow(true)
    }

    return () => {
      window.removeEventListener('beforeinstallprompt', onBip)
    }
  }, [])

  const install = useCallback(async () => {
    if (!deferred) return
    await deferred.prompt()
    try {
      await deferred.userChoice
    } catch {
      /* ignore */
    }
    setDeferred(null)
    setShow(false)
  }, [deferred])

  const dismiss = useCallback(() => {
    setShow(false)
    localStorage.setItem(DISMISS_KEY, '1')
  }, [])

  if (standalone || !show) return null

  return (
    <div
      role="dialog"
      aria-label="Install Boardman"
      style={{
        position: 'fixed',
        left: 12,
        right: 12,
        bottom: 'calc(5.5rem + env(safe-area-inset-bottom))',
        zIndex: 60,
        maxWidth: 28 * 16,
        margin: '0 auto',
        borderRadius: 16,
        border: '1px solid rgba(52,211,153,0.35)',
        background: 'rgba(7,8,12,0.96)',
        boxShadow: '0 16px 40px rgba(0,0,0,0.5)',
        padding: '0.9rem 1rem',
        color: '#f3f4f6',
        fontFamily: 'system-ui, sans-serif',
      }}
    >
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/rematch/icon-192.png"
          alt=""
          width={44}
          height={44}
          style={{ borderRadius: 12, flexShrink: 0 }}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ margin: 0, fontWeight: 800, fontSize: '0.95rem' }}>
            Add Boardman to Home Screen
          </p>
          <p style={{ margin: '0.3rem 0 0', fontSize: '0.78rem', color: '#9ca3af', lineHeight: 1.4 }}>
            {isIos && !deferred
              ? 'Tap Share → Add to Home Screen for a full-screen Boardman app.'
              : 'Install for one-tap play — Boardman only, not the full sideQuest site.'}
          </p>
          <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
            {deferred ? (
              <button
                type="button"
                onClick={install}
                style={{
                  border: 'none',
                  borderRadius: 999,
                  padding: '0.45rem 0.9rem',
                  fontWeight: 700,
                  fontSize: '0.8rem',
                  background: 'linear-gradient(180deg,#12c48a,#059669)',
                  color: '#fff',
                  cursor: 'pointer',
                }}
              >
                Install
              </button>
            ) : null}
            <button
              type="button"
              onClick={dismiss}
              style={{
                border: '1px solid rgba(255,255,255,0.12)',
                borderRadius: 999,
                padding: '0.45rem 0.9rem',
                fontWeight: 600,
                fontSize: '0.8rem',
                background: 'transparent',
                color: '#d1d5db',
                cursor: 'pointer',
              }}
            >
              Not now
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
