import { NextResponse } from 'next/server'
import { createClient } from '@supabase/supabase-js'

/**
 * Public Rematch leaderboard + open challenges + chain metrics.
 * Uses service role when available; falls back to anon (may be empty under RLS).
 */
export const dynamic = 'force-dynamic'
export const revalidate = 0

function sb() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || ''
  const key =
    process.env.SUPABASE_SERVICE_ROLE_KEY ||
    process.env.SUPABASE_SERVICE_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
    process.env.SUPABASE_ANON ||
    ''
  if (!url || !key) throw new Error('Supabase not configured')
  return createClient(url, key, { auth: { persistSession: false } })
}

function reputation(wins: number, losses: number, draws: number, play: number) {
  const total = Math.max(0, wins + losses + draws)
  let base = total === 0 ? 50 : Math.floor(40 + (wins / total) * 45)
  base += Math.min(10, Math.floor(play / 1000))
  return Math.max(0, Math.min(100, base))
}

function tierFrom(play: number) {
  if (play >= 10000) return 'diamond'
  if (play >= 5000) return 'platinum'
  if (play >= 2000) return 'gold'
  if (play >= 500) return 'silver'
  return 'bronze'
}

export async function GET() {
  try {
    const client = sb()

    // Leaderboard
    const { data: profiles, error: pErr } = await client
      .from('profiles')
      .select(
        'id,display_name,gaming_tag,play_points,play_win_streak,gaming_wins,gaming_losses,gaming_draws'
      )
      .gt('play_points', 0)
      .order('play_points', { ascending: false })
      .limit(40)

    if (pErr) console.warn('[rematch/public] profiles', pErr.message)

    const leaderboard = (profiles || []).map((row: any, i: number) => {
      const wins = Number(row.gaming_wins || 0)
      const losses = Number(row.gaming_losses || 0)
      const draws = Number(row.gaming_draws || 0)
      const play = Number(row.play_points || 0)
      return {
        rank: i + 1,
        tag: row.gaming_tag || '—',
        name: row.display_name || 'Player',
        play_points: play,
        tier: tierFrom(play),
        reputation: reputation(wins, losses, draws, play),
        wins,
        losses,
        draws,
        streak: Number(row.play_win_streak || 0),
      }
    })

    // Open public challenges (gaming schema)
    let open_challenges: any[] = []
    try {
      const { data: challenges, error: cErr } = await client
        .schema('gaming')
        .from('challenges')
        .select(
          'id,public_code,status,stake_amount,game_type,settlement_chain,issuer_id,target_id,theme,created_at'
        )
        .eq('status', 'open')
        .order('created_at', { ascending: false })
        .limit(60)

      if (cErr) console.warn('[rematch/public] challenges', cErr.message)

      const issuerIds = Array.from(
        new Set((challenges || []).map((c: any) => c.issuer_id).filter(Boolean))
      )
      let tagMap: Record<string, string> = {}
      if (issuerIds.length) {
        const { data: tags } = await client
          .from('profiles')
          .select('id,gaming_tag,display_name')
          .in('id', issuerIds)
        for (const t of tags || []) {
          tagMap[t.id] = t.gaming_tag || t.display_name || 'player'
        }
      }

      open_challenges = (challenges || [])
        .filter((c: any) => {
          const vis = String(c.theme || 'private').toLowerCase()
          return vis === 'public' && !c.target_id
        })
        .slice(0, 25)
        .map((c: any) => ({
          code: c.public_code || String(c.id || '').slice(0, 8),
          stake: Number(c.stake_amount || 0),
          game: c.game_type || 'EAFC',
          chain: c.settlement_chain || 'arc',
          creator_tag: tagMap[c.issuer_id] || 'player',
          created_at: c.created_at,
        }))
    } catch (e: any) {
      console.warn('[rematch/public] open board', e?.message)
    }

    // Metrics from resolved
    const by_chain: Record<string, { matches: number; volume_usdc: number }> = {
      arc: { matches: 0, volume_usdc: 0 },
      base: { matches: 0, volume_usdc: 0 },
      avalanche: { matches: 0, volume_usdc: 0 },
    }
    let resolved_total = 0
    try {
      const { data: resolved } = await client
        .schema('gaming')
        .from('challenges')
        .select('stake_amount,settlement_chain,status')
        .eq('status', 'resolved')
        .limit(500)
      for (const row of resolved || []) {
        resolved_total += 1
        const chain = String(row.settlement_chain || 'base').toLowerCase()
        if (!by_chain[chain]) by_chain[chain] = { matches: 0, volume_usdc: 0 }
        by_chain[chain].matches += 1
        by_chain[chain].volume_usdc += Number(row.stake_amount || 0) * 2
      }
    } catch (e: any) {
      console.warn('[rematch/public] metrics', e?.message)
    }

    return NextResponse.json({
      leaderboard,
      open_challenges,
      metrics: { resolved_total, by_chain },
      updated_at: new Date().toISOString(),
    })
  } catch (e: any) {
    return NextResponse.json(
      { error: e?.message || 'failed', leaderboard: [], open_challenges: [], metrics: null },
      { status: 200 }
    )
  }
}
