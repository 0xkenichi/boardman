import type { MetadataRoute } from 'next'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/admin', '/api/', '/rematch/app'],
      },
    ],
    sitemap: 'https://boardman.playingsidequest.fun/sitemap.xml',
    host: 'https://boardman.playingsidequest.fun',
  }
}
