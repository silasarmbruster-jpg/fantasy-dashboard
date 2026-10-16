// Minimaler Service Worker, nur um die Seite installierbar zu machen
// (PWA-Kriterium). Cached die statische App-Shell für schnelles Laden;
// data.json wird bewusst IMMER frisch aus dem Netz geladen (network-only),
// damit nie veraltete Liga-Daten angezeigt werden.
const CACHE_NAME = "fantasy-hq-shell-v1";
const SHELL_FILES = ["./index.html", "./app.js", "./styles.css", "./manifest.json", "./icon-192.png", "./icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.endsWith("data.json")) {
    return; // immer Netz, kein Caching der Liga-Daten
  }
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
