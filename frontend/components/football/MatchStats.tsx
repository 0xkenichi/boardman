'use client'
import './matchstats.css'
import type { MatchStats as MatchStatsData } from '../../lib/afm'

interface Props {
  stats?: MatchStatsData
  homeName?: string
  awayName?: string
  homeColor?: string
  awayColor?: string
}

/** Render the engine's post-match stat fold (shots, corners, cards, …). */
export default function MatchStats({
  stats,
  homeName = 'Home',
  awayName = 'Away',
  homeColor = '#4ade80',
  awayColor = '#f472b6',
}: Props) {
  if (!stats) return null
  const n = (k: string) => stats[k] ?? 0
  const possH = n('possession_home')
  const possA = n('possession_away')
  const total = possH + possA
  const homeShare = total > 0 ? (possH / total) * 100 : 50

  const rows: [string, string, string][] = [
    ['Shots', 'shots_home', 'shots_away'],
    ['On target', 'shots_on_target_home', 'shots_on_target_away'],
    ['Corners', 'corners_home', 'corners_away'],
    ['Fouls', 'fouls_home', 'fouls_away'],
    ['Offsides', 'offsides_home', 'offsides_away'],
    ['Yellow cards', 'yellow_cards_home', 'yellow_cards_away'],
    ['Red cards', 'red_cards_home', 'red_cards_away'],
  ]

  return (
    <div className="ms">
      <div className="ms-possession">
        <div className="ms-club ms-home" style={{ color: homeColor }}>
          {homeName}
        </div>
        <div className="ms-club ms-away" style={{ color: awayColor }}>
          {awayName}
        </div>
        <div className="ms-possession-bar">
          <div className="ms-possession-fill" style={{ width: `${homeShare}%`, background: homeColor }} />
        </div>
        <div className="ms-possession-nums">
          <span style={{ color: homeColor }}>{Math.round(homeShare)}%</span>
          <span>{Math.round(100 - homeShare)}%</span>
        </div>
        <div className="ms-possession-label">possession</div>
      </div>
      <div className="ms-rows">
        {rows.map(([label, homeKey, awayKey]) => (
          <div className="ms-row" key={label}>
            <span className="ms-val ms-home-val">{n(homeKey)}</span>
            <span className="ms-label">{label}</span>
            <span className="ms-val ms-away-val">{n(awayKey)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
