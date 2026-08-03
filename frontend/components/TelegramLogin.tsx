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
 * BotFather: /setdomain for playingsidequest.fun
 */
export function TelegramLogin({ botUsername, onAuth, onMissing }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!botUsername) {
      onMissing?.()
      return
    }
    window.onTelegramAuth = (user) => {
      onAuth(user)
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
      delete window.onTelegramAuth
    }
  }, [botUsername, onAuth, onMissing])

  if (!botUsername) return null
  return <div ref={ref} style={{ display: 'flex', justifyContent: 'center', minHeight: 48 }} />
}
