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
    'Boardman by sideQuest — digital boardman for skill 1v1s. Lock stake, play, settle.',
  /** Public paths are clean (/); internal files still under app/rematch */
  pathPrefix: '',
  /** Canonical product host (set DNS → rematch-web on Vercel) */
  host: 'boardman.playingsidequest.fun',
  /** Full marketing URL once DNS is live */
  url: 'https://boardman.playingsidequest.fun',
  /** One inbox — support, press, builders, partners */
  email: 'boardman@playingsidequest.fun',
  /** Primary logo path */
  logo: '/boardman-logo.jpg',
  logoPng: '/boardman-logo.png',
} as const

export type Brand = typeof BRAND
