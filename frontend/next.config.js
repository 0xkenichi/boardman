/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    unoptimized: true,
  },
  // Clean Boardman URLs are handled in middleware (rewrite / → /rematch, /app → /rematch/app).
  // No root redirect to /rematch — that would break boardman.playingsidequest.fun/
  async redirects() {
    return []
  },
  async rewrites() {
    return []
  },
}

module.exports = nextConfig
