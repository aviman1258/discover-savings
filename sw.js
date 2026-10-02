/* Service worker: cache-first over a fixed asset list.
 *
 * Two jobs. It's what makes Chrome offer "Install" rather than just "Add to
 * Home screen", and it's what makes the installed app open with no network.
 *
 * ============================================================
 *  BUMP CACHE_VERSION AFTER EVERY CHANGE YOU DEPLOY.
 *  Otherwise the installed app keeps serving the old files
 *  forever and looks like it didn't update.
 * ============================================================
 */

var CACHE_VERSION = 'v12';
var CACHE = 'discover-savings-' + CACHE_VERSION;

// Local development is network-first, so editing a file and reloading just
// works. Without this the cache below serves your old files back to you and it
// looks like your changes did nothing -- which is exactly what happened during
// the build of this app.
//
// Production stays cache-first, because that's what makes the installed app
// open instantly and work with no signal.
var DEV = self.location.hostname === 'localhost' || self.location.hostname === '127.0.0.1';

// Relative paths throughout. GitHub Pages serves from a subpath, so a leading
// slash would resolve to the domain root and 404.
var ASSETS = [
  './',
  './index.html',
  './css/app.css',
  './js/config.js',
  './js/data.js',
  './js/app.js',
  './manifest.webmanifest',
  './img/wordmark.png',
  './img/wordmark-white.png',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-maskable-512.png'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(ASSETS);
    }).then(function () {
      // Take over immediately instead of waiting for every tab to close.
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (names) {
      return Promise.all(names.map(function (name) {
        if (name !== CACHE) return caches.delete(name);
      }));
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener('fetch', function (event) {
  var request = event.request;

  // Only GETs are cacheable, and cross-origin requests aren't ours to serve.
  if (request.method !== 'GET' || new URL(request.url).origin !== self.location.origin) {
    return;
  }

  function fromNetwork() {
    return fetch(request).then(function (response) {
      // Only stash real, complete responses.
      if (response && response.status === 200 && response.type === 'basic') {
        var copy = response.clone();
        caches.open(CACHE).then(function (cache) { cache.put(request, copy); });
      }
      return response;
    });
  }

  function fromCache() {
    return caches.match(request).then(function (hit) {
      if (hit) return hit;
      // Offline and not in cache. For a page request, hand back the shell so
      // the app still opens; anything else genuinely fails.
      if (request.mode === 'navigate') return caches.match('./index.html');
      return Response.error();
    });
  }

  if (DEV) {
    // Network wins; cache is only the offline fallback.
    event.respondWith(fromNetwork().catch(fromCache));
    return;
  }

  event.respondWith(
    caches.match(request).then(function (hit) {
      return hit || fromNetwork().catch(fromCache);
    })
  );
});
