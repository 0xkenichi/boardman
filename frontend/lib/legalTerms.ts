/**
 * Turns the counsel draft of the Terms (docs/TERMS_OF_SERVICE.md, mirrored
 * byte-for-byte at frontend/content/legal/TERMS_OF_SERVICE.md) into the text
 * published at /terms.
 *
 * The draft carries `[COUNSEL: …]` markers. They are notes for the lawyer,
 * not terms, so the public page drops them. A few sit where the sentence
 * needs words, and those get a neutral placeholder below. When counsel
 * resolves a marker in the markdown, its rule here simply stops matching.
 *
 * Pure string work, no imports, so `node --test` can load it.
 */

export const LEGAL_EMAIL = 'boardman@playingsidequest.fun'
export const OPERATOR_PLACEHOLDER = 'sideQuest (legal entity details available on request)'

const MARKER = /\[COUNSEL:[^\]]*\]/

/** [pattern, replacement] applied in order before the generic strip. */
const PLACEHOLDERS: Array<[RegExp, string]> = [
  [/\[COUNSEL: set on publication\]/, '15 October 2026'],
  // Operator line: keep it its own paragraph and name the operator plainly.
  [/\n\*\*Operator:\*\* sideQuest \[COUNSEL:[^\]]*\]/, `\n\n**Operator:** ${OPERATOR_PLACEHOLDER}`],
  [/Where these differ, \[COUNSEL: which governs[^\]]*\]/, 'Where these differ, contact us and we will reconcile them'],
  [/subject to\s+\[COUNSEL: appeal[^\]]*\]/, 'subject to any rights you have under the law that applies to you'],
  [
    /\[COUNSEL: choose the governing law[^\]]*\]/,
    `Details of the governing law and the forum for disputes are available on request from ${LEGAL_EMAIL}.`,
  ],
  [/Legal notices: \[COUNSEL:[^\]]*\]/, `Legal notices: ${LEGAL_EMAIL}`],
  // Pointers into the internal repo docs mean nothing on the public site.
  [/\s*See the KYC plan:\s*\[[^\]]*\]\([^)]*\)\./, ''],
]

export function publishTerms(md: string): string {
  let s = md.replace(/\r\n?/g, '\n')

  // Drop the title line and the internal "DRAFT — NOT LEGAL ADVICE" banner;
  // the page supplies its own heading.
  s = s.replace(/^# [^\n]*\n+/, '')
  s = s.replace(/^(?:>[^\n]*\n)+\n*/, '')

  for (const [pattern, replacement] of PLACEHOLDERS) s = s.replace(pattern, replacement)

  // Every remaining marker is a note to counsel: remove it with its leading space.
  s = s.replace(new RegExp(`[ \\t]*\\n?[ \\t]*${MARKER.source}`, 'g'), '')

  // Bullets or paragraphs that held only a marker are now empty.
  s = s.replace(/^\s*-\s*$/gm, '')
  return s.replace(/\n{3,}/g, '\n\n').trim() + '\n'
}
