import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'The board',
  description: 'Who is up and who is down on Boardman — settled wins, streaks and volume, straight from the book.',
  alternates: { canonical: 'https://boardman.playingsidequest.fun/leaderboard' },
}

export default function LeaderboardLayout({ children }: { children: React.ReactNode }) {
  return children
}
