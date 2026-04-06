const CACHE_NAME = "traducteur-v2";
const ASSETS = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/static/manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // API calls: always go to network
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  // Images: cache-first
  if (url.pathname.match(/\.png$/)) {
    e.respondWith(
      caches.match(e.request).then((cached) => {
        if (cached) return cached;
        return fetch(e.request).then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(e.request, clone));
          return response;
        });
      })
    );
    return;
  }

  // JS/CSS and everything else: stale-while-revalidate
  const cachePromise = caches.match(e.request);

  // Kick off the network fetch immediately and extend the event lifetime so
  // the background cache write is allowed to complete even after we have
  // already responded with the stale entry.
  const networkFetch = fetch(e.request).then((response) => {
    const clone = response.clone();
    return caches.open(CACHE_NAME).then((cache) => cache.put(e.request, clone));
  }).catch(() => {});

  e.waitUntil(networkFetch);

  e.respondWith(
    cachePromise.then((cached) => {
      if (cached) return cached;
      // No cached entry yet — wait for the network response.
      return fetch(e.request).then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(e.request, clone));
        return response;
      });
    })
  );
});
