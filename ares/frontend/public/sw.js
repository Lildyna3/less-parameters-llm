/* ARES service worker.

   Deliberately conservative: it caches only the application shell (HTML, JS,
   CSS, icons) so the app launches instantly and survives a flaky connection.

   It NEVER caches /api/* or WebSocket traffic. Market data, account state,
   positions and news must always come from the network — a cached price is a
   wrong price, and showing one would be indistinguishable from fabricating it.
   When the network is unavailable the app says so instead. */

const VERSION = "ares-shell-v1";
const SHELL = ["/", "/index.html", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(VERSION)
      .then((cache) => cache.addAll(SHELL).catch(() => undefined))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== VERSION).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Live data is never served from cache.
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws") ||
      url.pathname.startsWith("/bridge")) {
    return;
  }

  // Navigations: network first so a deploy is picked up immediately, with the
  // cached shell as the offline fallback.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          void caches.open(VERSION).then((cache) => cache.put("/index.html", copy));
          return response;
        })
        .catch(() => caches.match("/index.html").then((hit) => hit ?? Response.error())),
    );
    return;
  }

  // Hashed build assets are immutable: serve from cache, populate on miss.
  event.respondWith(
    caches.match(request).then((hit) => {
      if (hit) return hit;
      return fetch(request).then((response) => {
        if (response.ok && (url.pathname.startsWith("/assets/") || SHELL.includes(url.pathname))) {
          const copy = response.clone();
          void caches.open(VERSION).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    }),
  );
});
