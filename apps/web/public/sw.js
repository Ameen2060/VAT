/* Service worker for the VAT Compliance PWA.
 *
 * Design priority: correctness for a live financial app over aggressive caching.
 * - /api/* and /health are NEVER cached — always hit the network so data and auth
 *   are always fresh (a stale cached balance or token would be dangerous).
 * - Immutable, content-hashed build assets (/_next/static, /icons, fonts) are
 *   cache-first for instant repeat loads.
 * - Page navigations are network-first, falling back to an offline page only when
 *   the device is truly offline.
 */
const VERSION = "v3";
const STATIC_CACHE = `vat-static-${VERSION}`;
const OFFLINE_URL = "/offline.html";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll([OFFLINE_URL, "/icons/icon-192.png"])),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== STATIC_CACHE).map((k) => caches.delete(k))),
      )
      .then(() => self.clients.claim()),
  );
});

function isImmutableAsset(url) {
  return (
    url.pathname.startsWith("/_next/static/") ||
    url.pathname.startsWith("/icons/") ||
    url.pathname.startsWith("/fonts/") ||
    url.pathname === "/manifest.webmanifest"
  );
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Only handle same-origin requests; let cross-origin (and the backend proxy) pass through.
  if (url.origin !== self.location.origin) return;

  // Never cache API / health / auth traffic — always go to the network.
  if (url.pathname.startsWith("/api/") || url.pathname === "/health") return;

  // Immutable build assets: cache-first with background refresh.
  if (isImmutableAsset(url)) {
    event.respondWith(
      caches.open(STATIC_CACHE).then(async (cache) => {
        const cached = await cache.match(req);
        const network = fetch(req)
          .then((res) => {
            if (res && res.ok) cache.put(req, res.clone());
            return res;
          })
          .catch(() => cached);
        return cached || network;
      }),
    );
    return;
  }

  // Page navigations: network-first, fall back to the offline page when offline.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() => caches.match(OFFLINE_URL).then((r) => r || Response.error())),
    );
  }
});

// Allow the page to trigger an immediate activation of a new worker.
self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting();
});
