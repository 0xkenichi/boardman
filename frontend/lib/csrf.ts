/**
 * Cross-site request refusal for the cookie-authenticated BFF (/api/**).
 *
 * The session cookie is SameSite=Lax, which keeps it off cross-site POSTs
 * but not off:
 *   - same-SITE requests from any other *.playingsidequest.fun origin
 *     (SameSite is per site, not per origin), and
 *   - login CSRF: a cross-site top-level form POST needs no cookie at all,
 *     and a text/plain form can carry a valid JSON body (the route parses
 *     it with req.json() whatever the Content-Type), so an attacker could
 *     sign a victim into the attacker's own account.
 *
 * So every unsafe /api request must come from this exact origin. Browsers
 * send Sec-Fetch-Site and Origin on these requests; server-to-server
 * callers (no browser, no victim cookies) send neither and pass. Signed
 * provider webhooks are exempt (they authenticate with an HMAC).
 *
 * Pure function (no Next imports) so node --test can run it.
 */

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

/** Signed by their provider, called server-to-server: no Origin to check. */
export const CSRF_EXEMPT_PREFIXES = ['/api/rematch/paystack/webhook']

/** Body types a cross-site HTML form can send without a CORS preflight. */
const FORM_TYPES = /^\s*(text\/plain|application\/x-www-form-urlencoded)\b/i

type HeaderBag = { get(name: string): string | null }

export function crossSiteRefusal(
  method: string,
  pathname: string,
  headers: HeaderBag,
  host: string
): string | null {
  if (SAFE_METHODS.has((method || '').toUpperCase())) return null
  if (CSRF_EXEMPT_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/'))) return null

  const site = (headers.get('sec-fetch-site') || '').toLowerCase()
  if (site && site !== 'same-origin' && site !== 'none') return 'cross_site_request'

  const origin = headers.get('origin')
  if (origin !== null) {
    let originHost = ''
    try {
      originHost = new URL(origin).host.toLowerCase()
    } catch {
      return 'bad_origin' // includes the opaque "null" origin
    }
    if (!host || originHost !== host.toLowerCase()) return 'origin_mismatch'
  }

  if (FORM_TYPES.test(headers.get('content-type') || '')) return 'form_content_type'
  return null
}
