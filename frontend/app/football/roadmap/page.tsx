import type { Metadata } from 'next'
import { PortalNav } from '@/components/football/PortalNav'
import {
  BUILD_ORDER,
  GOALS,
  OBJECTIVE,
  SECTIONS,
  STATUS_META,
  overallCounts,
  sectionCounts,
} from '@/lib/afm-roadmap'
import '../portal.css'

export const metadata: Metadata = {
  title: 'Roadmap · Agentic Football Managers',
  description:
    'The live status board of the AFM master plan: what is done, what needs work, what is a must, and what is an add-on — engine, agent tools, broadcast, voice and rails.',
  robots: { index: false, follow: false },
}

const STATUS_ORDER = ['done', 'needs-work', 'must', 'add-on', 'parked'] as const

export default function RoadmapPage() {
  const counts = overallCounts()
  const legend = STATUS_ORDER.filter((s) => counts[s] > 0 || s === 'must')

  return (
    <div className="fd-wrap">
      <PortalNav active="/football/roadmap" />

      <div className="fd-hero">
        <h1 style={{ fontSize: 30 }}>The master plan — live status</h1>
        <p className="fd-lede">
          One deterministic engine feeding two products that never touch: agents in Football
          Manager, humans in a broadcast. This board is the living todo — every row below is a
          real feature with a real status, kept in sync with the code.
        </p>
      </div>

      {/* Objective + legend + counts */}
      <div className="fd-sect">
        <h2>Objective</h2>
        <p className="fd-sub">{OBJECTIVE}</p>
        <div className="rm-legend">
          {legend.map((s) => {
            const m = STATUS_META[s]
            return (
              <span className="rm-legend-chip" key={s}>
                <span className={`rm-badge rm-${s}`}>
                  {m.mark} {m.label}
                </span>
                <b>{counts[s]}</b> item{counts[s] === 1 ? '' : 's'}
              </span>
            )
          })}
        </div>
      </div>

      {/* Goals */}
      <div className="fd-sect">
        <h2>Goals — how we know it’s met</h2>
        <div className="rm-goals">
          {GOALS.map((g) => (
            <div className="rm-goal" key={g.id}>
              <h4>
                <span className="rm-goal-id">{g.id}</span> {g.title}
              </h4>
              <p>{g.proof}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Sections */}
      {SECTIONS.map((sec) => {
        const c = sectionCounts(sec)
        return (
          <div className="fd-sect" key={sec.id}>
            <h2>{sec.title}</h2>
            {sec.tagline && <p className="fd-sub">{sec.tagline}</p>}
            {sec.banner && (
              <div className="rm-banner">
                <span className={`rm-badge rm-${sec.banner.status}`}>
                  {STATUS_META[sec.banner.status].mark} {sec.banner.text}
                </span>
              </div>
            )}
            <div className="rm-items">
              {sec.items.map((it) => {
                const m = STATUS_META[it.status]
                return (
                  <div className="rm-item" key={it.label}>
                    <span className={`rm-badge rm-${it.status}`}>
                      {m.mark} {m.label}
                    </span>
                    <div className="rm-item-main">
                      <b>{it.label}</b>
                      {it.note && <span>{it.note}</span>}
                    </div>
                  </div>
                )
              })}
            </div>
            <p className="rm-mini">
              {STATUS_META.done.mark} {c.done} done · {STATUS_META['needs-work'].mark} {c['needs-work']} needs work ·{' '}
              {STATUS_META.must.mark} {c.must} must · {STATUS_META['add-on'].mark} {c['add-on']} add-on
              {c.parked ? ` · ${STATUS_META.parked.mark} ${c.parked} parked` : ''}
            </p>
          </div>
        )
      })}

      {/* Build order */}
      <div className="fd-sect">
        <h2>Build order</h2>
        <p className="fd-sub">
          Per current direction: the 2D broadcast is the focus; 3D is parked. The engine spatial
          work is the honest prerequisite for both products, so it is Phase 1.
        </p>
        <div className="rm-phases">
          {BUILD_ORDER.map((p) => (
            <div className="rm-phase" key={p.id}>
              <h4>
                <span className="rm-phase-id">{p.id}</span> {p.name}
              </h4>
              <p className="rm-phase-scope">{p.scope}</p>
              <p className="rm-phase-done">
                <b>Done when:</b> {p.done}
              </p>
            </div>
          ))}
        </div>
      </div>

      <p className="fd-foot">
        Source of truth: <code>docs/games/AGENTIC_FOOTBALL_MANAGERS_ROADMAP.md</code> — this board
        mirrors it so the status lives in the product. Acceptance test for the whole split: mute
        every UI label — the agent still knows what to do from numbers; the human still
        understands who is winning and why the game flipped.
      </p>
    </div>
  )
}