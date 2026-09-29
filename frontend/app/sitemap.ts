import type { MetadataRoute } from 'next'

const BASE = 'https://boardman.playingsidequest.fun'

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date()
  return [
    { url: BASE, lastModified: now, changeFrequency: 'daily', priority: 1 },
    { url: `${BASE}/how-it-works`, lastModified: now, changeFrequency: 'monthly', priority: 0.9 },
    { url: `${BASE}/games`, lastModified: now, changeFrequency: 'weekly', priority: 0.8 },
    { url: `${BASE}/arena`, lastModified: now, changeFrequency: 'hourly', priority: 0.9 },
    { url: `${BASE}/questions`, lastModified: now, changeFrequency: 'monthly', priority: 0.7 },
    { url: `${BASE}/about`, lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${BASE}/builders`, lastModified: now, changeFrequency: 'weekly', priority: 0.6 },
    { url: `${BASE}/app`, lastModified: now, changeFrequency: 'daily', priority: 0.9 },
    { url: `${BASE}/leaderboard`, lastModified: now, changeFrequency: 'daily', priority: 0.5 },
    { url: `${BASE}/get-usdc`, lastModified: now, changeFrequency: 'monthly', priority: 0.4 },
    { url: `${BASE}/contact`, lastModified: now, changeFrequency: 'monthly', priority: 0.5 },
  ]
}
