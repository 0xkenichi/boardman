import fs from 'node:fs'
import path from 'node:path'
import type { Metadata } from 'next'
import { BookShell } from '@/components/rematch/BookShell'
import { LegalMarkdown } from '@/components/rematch/LegalMarkdown'
import { parseMarkdown } from '@/lib/legalMarkdown'
import { publishTerms } from '@/lib/legalTerms'

export const metadata: Metadata = {
  title: 'Terms of Service',
  description:
    'The rules of the table: who can play, how your play wallet and stakes work, fees, disputes and the risks of playing on Boardman.',
  alternates: { canonical: 'https://boardman.playingsidequest.fun/terms' },
}

export const dynamic = 'force-static'

/**
 * Single source of truth: docs/TERMS_OF_SERVICE.md, mirrored into
 * frontend/content/legal (npm run sync:legal; CI checks they match).
 * Read once at build; counsel notes are dropped by publishTerms.
 */
function loadTerms() {
  const file = path.join(process.cwd(), 'content', 'legal', 'TERMS_OF_SERVICE.md')
  return parseMarkdown(publishTerms(fs.readFileSync(file, 'utf8')))
}

export default function TermsPage() {
  return (
    <BookShell title="Terms of Service">
      <article className="bk-legal">
        <p className="bk-legal-meta">
          THE RULES OF THE TABLE · READ WITH THE <a href="/privacy">PRIVACY POLICY</a>
        </p>
        <LegalMarkdown blocks={loadTerms()} />
      </article>
    </BookShell>
  )
}
