/* Boardman service worker — scope / */
const CACHE = 'boardman-v3-purge'
const PRECACHE = [
  '/manifest.webmanifest',
  '/rematch/manifest.webmanifest',
  '/rematch/icon-192.png',
  '/rematch/icon-512.png',
  '/rematch/icon-180.png',
  '/app',
  '/',
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(PRECACHE).catch(() => undefined))
      .then(() => self.skipWaiting())
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => (k.startsWith('rematch-') || k.startsWith('boardman-')) && k !== CACHE)
            .map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return

  const url = new URL(req.url)
  if (url.origin !== self.location.origin) return
  if (
    url.pathname.startsWith('/admin') ||
    url.pathname.startsWith('/api/agentic') ||
    url.pathname.indexOf('metrics') !== -1 ||
    url.pathname.indexOf('match-proofs') !== -1
  ) {
    event.respondWith(fetch(req, { cache: 'no-store' }))
    return
  }

  const isDoc =
    req.mode === 'navigate' ||
    (req.headers.get('accept') || '').includes('text/html') ||
    url.pathname.startsWith('/api/rematch')

  if (isDoc) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone()
          if (res.ok && req.mode === 'navigate') {
            caches.open(CACHE).then((c) => c.put('/app', copy)).catch(() => {})
          }
          return res
        })
        .catch(() => caches.match(req).then((c) => c || caches.match('/app') || caches.match('/')))
    )
    return
  }

  if (
    url.pathname.startsWith('/rematch/icon-') ||
    url.pathname.endsWith('manifest.webmanifest') ||
    url.pathname === '/sw.js' ||
    url.pathname === '/boardman-logo.jpg' ||
    url.pathname === '/boardman-logo.png'
  ) {
    event.respondWith(
      caches.match(req).then(
        (cached) =>
          cached ||
          fetch(req).then((res) => {
            const copy = res.clone()
            caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {})
            return res
          })
      )
    )
  }
})
