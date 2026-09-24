// Service worker: makes the app work offline after the first visit.
// Bump CACHE when index.html, data/charsets.json or fonts/kai.woff2 changes so devices pick up the new version.
const CACHE = 'hanzi-garden-v5';
const CORE = ['./privacy.html', './', './index.html', './data/charsets.json', './fonts/kai.woff2', './manifest.webmanifest', './icon-180.png', './icon-192.png', './icon-512.png'];

self.addEventListener('install', (e) => {
  // Bypass the HTTP cache so a new version never stores a stale copy of a file from the previous one.
  const fresh = CORE.map((u) => new Request(u, { cache: 'reload' }));
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(fresh)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  if (url.origin === self.location.origin) {
    if (req.mode === 'navigate') {
      // Network first for the page so updates show up; fall back to cache offline.
      e.respondWith(
        fetch(req)
          .then((res) => { const copy = res.clone(); caches.open(CACHE).then((c) => c.put('./index.html', copy)); return res; })
          .catch(() => caches.match('./index.html')));
      return;
    }
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
    return;
  }

  // Google Fonts (UI font, KaiTi fallback, color emoji): cache on first use.
  if (url.hostname.endsWith('fonts.googleapis.com') || url.hostname.endsWith('fonts.gstatic.com')) {
    e.respondWith(caches.open(CACHE).then(async (c) => {
      const hit = await c.match(req);
      const net = fetch(req)
        .then((res) => { if (res.ok || res.type === 'opaque') c.put(req, res.clone()); return res; })
        .catch(() => hit);
      return hit || net;
    }));
  }
});
