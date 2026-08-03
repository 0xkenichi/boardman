/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    unoptimized: true,
  },
  // If this project is served at the domain root (rematch.playingsidequest.fun
  // or vercel.app), /rematch/* still works. Optional rewrite for convenience:
  async redirects() {
    return [
      {
        source: '/',
        destination: '/rematch/app',
        permanent: false,
      },
    ]
  },
  async rewrites() {
    // Proxy Stack/API in production when STACK is same-origin optional —
    // primary path is REMATCH_API_URL server-side env on BFF routes.
    return []
  },
}

module.exports = nextConfig
