import { redirect } from 'next/navigation'

/** Legacy URL → Rematch */
export default function ClawStationRedirect() {
  redirect('/rematch')
}
