'use client'

import { useEffect, useRef } from 'react'

declare global {
  interface Window {
    onTelegramAuth?: (user: Record<string, string | number>) => void
  }
}

type Props = {
  botUsername: string
  onAuth: (user: Record<string, string | number>) => void
  onMissing?: () => void
}

/**
 * Official Telegram Login Widget.
 * BotFather: /setdomain for the host that serves /rematch (e.g. playingsidequest.fun)
 */
export function TelegramLogin({ botUsername, onAuth, onMissing }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const onAuthRef = useRef(onAuth)
  const onMissingRef = useRef(onMissing)
  onAuthRef.current = onAuth
  onMissingRef.current = onMissing

  useEffect(() => {
    if (!botUsername) {
      onMissingRef.current?.()
      return
    }
    // Stable global for Telegram's data-onauth string callback
    window.onTelegramAuth = (user) => {
      onAuthRef.current(user)
    }
    const script = document.createElement('script')
    script.src = 'https://telegram.org/js/telegram-widget.js?22'
    script.async = true
    script.setAttribute('data-telegram-login', botUsername)
    script.setAttribute('data-size', 'large')
    script.setAttribute('data-radius', '12')
    script.setAttribute('data-onauth', 'onTelegramAuth(user)')
    script.setAttribute('data-request-access', 'write')
    const el = ref.current
    if (el) {
      el.innerHTML = ''
      el.appendChild(script)
    }
    return () => {
      // keep handler if remounting; clear only on unmount of last instance
      if (window.onTelegramAuth) {
        // no-op safe cleanup
      }
    }
  }, [botUsername])

  if (!botUsername) return null
  return <div ref={ref} style={{ display: 'flex', justifyContent: 'center', minHeight: 48 }} />
}
