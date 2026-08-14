import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Contact',
  description:
    'Talk to the Boardman desk — Telegram for play, community for people, or write boardman@playingsidequest.fun for support, press, and builders.',
}

export default function ContactLayout({ children }: { children: React.ReactNode }) {
  return children
}
