import Link from 'next/link'
import { SeasonStrip } from './SeasonStrip'

const LINKS = [
  { href: '/football', label: 'Front door' },
  { href: '/football/watch', label: 'Watch' },
  { href: '/football/owner', label: 'Own a club' },
  { href: '/football/agent', label: 'The agents' },
  { href: '/football/league', label: 'League' },
  { href: '/football/tactics', label: 'Match board' },
  { href: '/football/roadmap', label: 'Roadmap' },
]

export function PortalNav({ active }: { active?: string }) {
  return (
    <>
      <nav className="fd-nav">
        <span className="fd-brand">⚽ AFM</span>
        {LINKS.map((l) => (
          <Link key={l.href} className={`fd-link${active === l.href ? ' fd-active' : ''}`} href={l.href}>
            {l.label}
          </Link>
        ))}
      </nav>
      <SeasonStrip active={active} />
    </>
  )
}
