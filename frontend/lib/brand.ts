/**
 * Boardman product brand (consumer-facing).
 * Company parent remains sideQuest. Technical paths may still use /rematch.
 */

export const BRAND = {
  /** Consumer product name */
  name: 'Boardman',
  /** Full lockup */
  fullName: 'Boardman by sideQuest',
  /** Parent company */
  parent: 'sideQuest',
  /** Short product line */
  tagline: 'Lock in. Play. Settle. Run it back.',
  /** Role line — cultural hook */
  role: 'Digital boardman for skill 1v1s',
  /** SEO / store description */
  description:
    'Digital boardman for skill 1v1s — both lock stake, play, final screen settles. by sideQuest.',
  /** Optional path prefix (routes still /rematch for stability) */
  pathPrefix: '/rematch',
} as const

export type Brand = typeof BRAND
