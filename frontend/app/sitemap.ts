import type { MetadataRoute } from 'next'

const BASE = 'https://boardman.playingsidequest.fun'

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date()
  return [
    { url: BASE, lastModified: now, changeFrequency: 'daily', priority: 1 },
    { url: `${BASE}/agentic/arena.html`, lastModified: now, changeFrequency: 'hourly', priority: 0.9 },
    { url: `${BASE}/llms.txt`, lastModified: now, changeFrequency: 'weekly', priority: 0.8 },
    { url: `${BASE}/agentic/docs.html`, lastModified: now, changeFrequency: 'weekly', priority: 0.7 },
    { url: `${BASE}/agentic/games.json`, lastModified: now, changeFrequency: 'weekly', priority: 0.6 },
    { url: `${BASE}/leaderboard`, lastModified: now, changeFrequency: 'daily', priority: 0.5 },
    { url: `${BASE}/get-usdc`, lastModified: now, changeFrequency: 'monthly', priority: 0.4 },
  ]
}
