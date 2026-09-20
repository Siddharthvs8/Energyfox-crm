/**
 * EnergyFox CRM — app-shell service worker.
 *
 * Two jobs: make the app installable and make it open instantly, even on a
 * site with no signal. It never caches API traffic — lead data is per-user and
 * behind a token, and a stale copy of somebody else's pipeline is worse than
 * an error message.
 */
const VERSION = 'energyfox-v1';
const SHELL = `${VERSION}-shell`;
const RUNTIME = `${VERSION}-runtime`;

/** Enough to paint the boot screen and start the engine. */
const SHELL_FILES = [
  './',
  'index.html',
  'manifest.json',
  'flutter_bootstrap.js',
  'flutter.js',
  'main.dart.js',
  'favicon.png',
  'icons/Icon-192.png',
  'icons/Icon-512.png',
  'icons/apple-touch-icon.png',
  'assets/assets/logo.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL).then((cache) =>
      // `addAll` is all-or-nothing, and one asset renamed by a Flutter upgrade
      // would then leave the app with no cache at all. Each file is fetched on
      // its own so a miss costs only that file.
      Promise.all(
        SHELL_FILES.map((file) =>
          cache.add(new Request(file, { cache: 'reload' })).catch(() => null)
        )
      )
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== SHELL && key !== RUNTIME)
          .map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('message', (event) => {
  if (event.data === 'skipWaiting') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  const sameOrigin = url.origin === self.location.origin;

  // Anything that smells like the CRM API stays on the network, always.
  if (!sameOrigin || url.pathname.includes('/api/') || url.pathname.includes('/media/')) {
    return;
  }

  // A navigation gets the network first so a deployed update lands straight
  // away, and the cached shell when there is nothing to reach.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(SHELL).then((cache) => cache.put('index.html', copy));
          return response;
        })
        .catch(() =>
          caches.match('index.html').then((cached) => cached || caches.match('./'))
        )
    );
    return;
  }

  // Everything else — the engine, CanvasKit, fonts, icons — is served from the
  // cache and refreshed in the background, so a cold start is instant and the
  // next one is up to date.
  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((response) => {
          if (response && response.status === 200 && response.type === 'basic') {
            const copy = response.clone();
            caches.open(RUNTIME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
