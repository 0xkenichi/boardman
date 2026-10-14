import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Play',
  description:
    'Call a 1v1, lock both stakes in escrow, play the game, get paid — the Boardman counter.',
  alternates: { canonical: 'https://boardman.playingsidequest.fun/app' },
}

export default function RematchAppLayout({ children }: { children: React.ReactNode }) {
  // The counter sits on the same cream paper as the rest of the book —
  // the old violet 3D desk scene is retired.
  return <div className="bm-app">{children}</div>
}
