// Service worker mínimo para PWA instalable
const CACHE = "sicavs-v1";
self.addEventListener("install", (e) => { self.skipWaiting(); });
self.addEventListener("activate", (e) => { e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", (e) => {
  // Estrategia: red primero (la app necesita datos en vivo)
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
