// Bump this version string whenever a shell asset (index.html / app.js / styles.css / icons)
// changes — cache-first would otherwise keep serving the old shell to installed clients.
const CACHE = "neuro-rag-v2";
const SHELL = ["/", "/index.html", "/styles.css", "/app.js",
  "/manifest.webmanifest", "/icons/icon-192.png", "/icons/apple-touch-icon.png",
  "/icons/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // Never cache answers or figure images — always go to the network.
  if(url.pathname.startsWith("/ask") || url.pathname.startsWith("/figures")) return;
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request)));
});
