/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow both loopback hosts for local dev resources (HMR, fonts, chunks).
  allowedDevOrigins: ['localhost', '127.0.0.1'],
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
