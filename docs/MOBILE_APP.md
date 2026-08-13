# Mobile App (PWA) & native-readiness

The web app is a **Progressive Web App**: installable on Android, iOS, iPadOS, Windows
and desktop, running standalone (no browser chrome) against the **same production
backend, database, auth and files** as the website. There is no separate codebase.

## What makes it an app

| Piece | File |
|-------|------|
| Web App Manifest (name, icons, standalone, theme) | [`apps/web/app/manifest.ts`](../apps/web/app/manifest.ts) |
| App icons (192/384/512 + maskable, Apple touch, favicons) | `apps/web/public/icons/` |
| Service worker (offline fallback, asset caching; never caches `/api`) | [`apps/web/public/sw.js`](../apps/web/public/sw.js) |
| Offline page | `apps/web/public/offline.html` |
| SW registration + Install button (Android prompt / iOS instructions) | [`apps/web/components/pwa.tsx`](../apps/web/components/pwa.tsx) |
| Viewport, theme-color, Apple web-app meta, boot splash | `apps/web/app/layout.tsx`, `components/app-shell.tsx` |

**Install:** Chrome/Edge/Android/desktop show an "Install app" button (and the browser's
own install icon). iOS Safari: Share → Add to Home Screen (the button shows instructions).

**Data safety:** the service worker is deliberately conservative — API, auth and health
traffic always go to the network; only content-hashed build assets are cached. No
accounting data is ever stored in the cache. Auth tokens live in `localStorage` as before.

## Native packaging readiness (Capacitor)

The project is structured so the *same* build can later be wrapped as a native
Android/iOS app without a rewrite, because:

- The API is reached through a single indirection. In the browser PWA, calls are
  same-origin `/api/*` (proxied by Next to the backend). `lib/api.ts` already honours
  `NEXT_PUBLIC_API_BASE` — for a native shell (which has no same-origin proxy) set
  `NEXT_PUBLIC_API_BASE=https://vat-ameen-api.vercel.app` so calls go directly to the
  production backend.
- The UI is fully responsive and touch-optimized already.

To package later (not installed now, to avoid changing the web build):

```bash
cd apps/web
npm i -D @capacitor/cli @capacitor/core @capacitor/android @capacitor/ios
npx cap init "VAT Compliance" app.vatameen.mobile --web-dir=out
# build a static export with NEXT_PUBLIC_API_BASE set to the production backend,
# then: npx cap add android && npx cap add ios && npx cap sync
```

Output targets: Android **APK/AAB** (Google Play) and iOS (App Store) — both load the
same UI and hit the same production backend, so accounting data is shared with the web
and PWA. No backend changes are required.
