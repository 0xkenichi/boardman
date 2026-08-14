import { NextResponse } from 'next/server'
import { promises as fs } from 'fs'
import path from 'path'
import { requireAdmin } from '@/lib/adminAuth'
import { supabaseRest } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

type Row = {
  email: string
  name?: string | null
  telegram?: string | null
  source?: string | null
  created_at?: string | null
}

async function readJsonFile(file: string): Promise<Row[]> {
  try {
    const raw = await fs.readFile(file, 'utf8')
    const rows = JSON.parse(raw)
    return Array.isArray(rows) ? rows : []
  } catch {
    return []
  }
}

export async function GET(req: Request) {
  const auth = requireAdmin(req)
  if ('error' in auth) return auth.error

  const local = await readJsonFile(path.join(process.cwd(), 'data', 'waitlist.json'))
  const tmp = await readJsonFile(path.join('/tmp', 'boardman-waitlist.json'))

  let remote: Row[] = []
  let via = 'local'
  const sb = await supabaseRest<Row[]>(
    'boardman_waitlist?select=email,name,telegram,source,created_at&order=created_at.desc&limit=500'
  )
  if (sb.ok && Array.isArray(sb.data)) {
    remote = sb.data
    via = 'supabase'
  }

  const seen = new Set<string>()
  const entries: Row[] = []
  for (const row of [...remote, ...local, ...tmp]) {
    const email = String(row?.email || '')
      .trim()
      .toLowerCase()
    if (!email || seen.has(email)) continue
    seen.add(email)
    entries.push({
      email,
      name: row.name || null,
      telegram: row.telegram || null,
      source: row.source || null,
      created_at: row.created_at || null,
    })
  }
  entries.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))

  return NextResponse.json(
    {
      ok: true,
      count: entries.length,
      via,
      entries,
    },
    { headers: { 'Cache-Control': 'no-store' } }
  )
}
