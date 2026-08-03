/* Rematch-only service worker — scope /rematch/ */
const CACHE = 'rematch-v1'
const PRECACHE = [
  '/rematch/manifest.webmanifest',
  '/rematch/icon-192.png',
  '/rematch/icon-512.png',
  '/rematch/icon-180.png',
  '/rematch/app',
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
        Promise.all(keys.filter((k) => k.startsWith('rematch-') && k !== CACHE).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return

  const url = new URL(req.url)
  // Only handle same-origin rematch scope
  if (url.origin !== self.location.origin) return
  if (!url.pathname.startsWith('/rematch')) return

  // Network-first for app shell / HTML / API so balances stay fresh
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
            caches.open(CACHE).then((c) => c.put('/rematch/app', copy)).catch(() => {})
          }
          return res
        })
        .catch(() => caches.match(req).then((c) => c || caches.match('/rematch/app')))
    )
    return
  }

  // Cache-first for static icons / manifest
  if (
    url.pathname.startsWith('/rematch/icon-') ||
    url.pathname.endsWith('manifest.webmanifest')
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
