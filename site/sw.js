// Minimaler Service Worker, nur um die Seite installierbar zu machen
// (PWA-Kriterium). Netzwerk-zuerst für die App-Shell (index.html/app.js/
// styles.css): die App ändert sich oft (tägliche Builds, laufende
// Entwicklung), ein reiner Cache-zuerst-Ansatz hätte bei jeder Änderung
// alte Versionen stehen lassen, bis jemand die Cache-Version manuell
// hochzählt - das ist bei der letzten Design-Überarbeitung genau so
// passiert. Netzwerk-zuerst behebt das dauerhaft: der Cache dient nur noch
// als Offline-Fallback, wird bei jedem erfolgreichen Laden aktualisiert.
// data.json bleibt komplett außen vor (immer frisch, nie gecacht), damit
// nie veraltete Liga-Daten angezeigt werden.
const CACHE_NAME = "fantasy-hq-shell-v2";
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
  if (url.origin !== location.origin) {
    return; // externe CDN-Ressourcen (Google Fonts, Lucide) nicht über den SW führen
  }
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
