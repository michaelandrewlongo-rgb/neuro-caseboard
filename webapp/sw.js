// KILL-SWITCH service worker.
//
// The previous worker precached the app shell and served it "cache-first", which
// meant `GET /` was answered from cache and never reached the server — serving a
// stale (dark, pre-passcode) shell offline and bypassing the /login redirect. A
// device in that state could not be rescued, because reaching the server was the
// one thing the cache-first worker prevented.
//
// This app needs the live server for every answer, so there is no useful offline
// mode and no reason to keep a worker. This file exists only to UNINSTALL the old
// one: it caches nothing, has no fetch handler (so every request goes straight to
// the network), then deletes all caches, unregisters itself, and reloads open
// tabs so they reload fresh from the server. Once it runs, no worker remains.
self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    await self.clients.claim();
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
    await self.registration.unregister();
    const clients = await self.clients.matchAll({ type: "window" });
    for (const client of clients) {
      // Reload each open tab so it fetches a fresh shell from the server with no
      // worker in control. Guarded: navigate() can reject on some browsers.
      client.navigate(client.url).catch(() => {});
    }
  })());
});
