# Deployment Guide — Vercel (frontend) + Render (backend)

Production topology. Nothing runs on a developer machine, a tunnel, or a local
terminal — the two hosts below run permanently and restart themselves.

| Piece | Host | URL |
|-------|------|-----|
| Next.js dashboard (`apps/web`) | **Vercel** | `https://vat-ameen.vercel.app` |
| FastAPI API + OCR (`apps/api`) | **Render** (Docker) | `https://vat-ameen-api.onrender.com` |
| PostgreSQL | Render managed DB (`vat-ameen-db`) | internal connection string |
| Uploaded files + generated reports | Render persistent disk at `/var/data` | internal |
| Daily FTA source monitor | Render cron (`vat-ameen-fta-monitor`) | 06:00 UTC |

Repository: **`github.com/Ameen2060/VAT`**, default branch `main`.

## How the frontend reaches the backend (important)

The browser only ever calls **`vat-ameen.vercel.app/api/*`** — same origin. Next.js
rewrites those requests **server-side** to the Render backend (see
[`apps/web/next.config.mjs`](../apps/web/next.config.mjs)). Consequences:

- **No CORS** is exercised by the browser (calls are same-origin).
- The client bundle contains **no backend hostname** — `lib/api.ts` uses relative
  `/api/...` paths (`API_BASE` defaults to `""`).
- The backend URL lives in exactly one place: the Vercel env var **`BACKEND_ORIGIN`**,
  which is baked into the routes manifest at **build time**. Changing the backend =
  update `BACKEND_ORIGIN` for all environments **and redeploy** (a rebuild).

---

## 1 — GitHub (done)

Code is on `github.com/Ameen2060/VAT` (`main`). Both hosts deploy from it.

## 2 — Backend on Render (Blueprint)

1. Render Dashboard → **New → Blueprint** → connect **`Ameen2060/VAT`**.
2. Render reads [`render.yaml`](../render.yaml) and proposes:
   - web service **`vat-ameen-api`** (Docker, `apps/api/Dockerfile`, Starter plan) with a
     1 GB persistent disk at `/var/data`, health check `/health`, auto-deploy on push.
   - PostgreSQL **`vat-ameen-db`**.
   - cron **`vat-ameen-fta-monitor`** (daily FTA source check).
3. Fill the three secret env vars it prompts for (see table below), then **Apply**.
   First build takes ~5–8 min (installs OCR + Postgres deps).
4. When live, copy the service URL (e.g. `https://vat-ameen-api.onrender.com`) and verify
   `…/health` returns `{"status":"ok"}`.

### Backend environment variables

Non-secret values are set automatically by `render.yaml`. Secrets (marked 🔒) are entered
in the Render dashboard and are never committed or printed.

| Variable | Set by | Value / meaning |
|----------|--------|-----------------|
| `DATABASE_URL` | blueprint (fromDatabase) | Postgres connection string; app normalizes `postgres://` → `postgresql+psycopg://` |
| `SECRET_KEY` | blueprint (generateValue) | JWT signing key, auto-generated |
| `APP_ENV` | blueprint | `production` |
| `STORAGE_BACKEND` | blueprint | `local` (persistent disk) |
| `LOCAL_STORAGE_DIR` | blueprint | `/var/data/storage` (on the disk) |
| `API_CORS_ORIGINS` | blueprint | `https://vat-ameen.vercel.app` |
| `APP_BASE_URL` | blueprint | `https://vat-ameen.vercel.app` (password-reset links) |
| `AI_PROVIDER` | blueprint | `anthropic` |
| `AI_MODEL` | blueprint | `claude-sonnet-5` |
| `ANTHROPIC_API_KEY` 🔒 | **you** | your Anthropic API key (app still runs without it via the deterministic engine) |
| `ADMIN_EMAIL` 🔒 | **you** | first-admin login email (bootstrapped on first boot) |
| `ADMIN_PASSWORD` 🔒 | **you** | first-admin password (8+ chars, upper + lower + digit) |

On first boot the backend creates all tables, seeds the official FTA sources + rules,
and bootstraps the admin user from `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

## 3 — Point Vercel at the backend and redeploy

Once the Render URL exists, set it for **all three** environments and rebuild:

```bash
cd apps/web
# for each of production / preview / development:
vercel env rm  BACKEND_ORIGIN <env> -y
echo "https://vat-ameen-api.onrender.com" | vercel env add BACKEND_ORIGIN <env>
vercel --prod
```

`BACKEND_ORIGIN` is the **only** Vercel env var this app needs. Do **not** set
`NEXT_PUBLIC_API_BASE` — the same-origin proxy design relies on it being empty.

## 4 — Smoke test (production, from a fresh browser)

1. Open `https://vat-ameen.vercel.app` → log in with the admin credentials.
2. Dashboard loads with live KPIs (proves frontend → Vercel proxy → Render → Postgres).
3. **Document Analysis** → upload an invoice → extraction + compliance verdict appear
   (proves upload + persistent disk + AI/deterministic engine).
4. Download a PDF report and an Excel export.
5. In Render, **Manual Deploy → Restart** the service, wait, refresh the site → the same
   data is still present (proves Postgres + disk persistence across restart).

---

## Notes

- **Always-on:** the Starter plan keeps `vat-ameen-api` warm and auto-restarts on crash;
  the persistent disk survives restarts and redeploys. Auto-deploy ships every push to
  `main`.
- **Free-tier variant (no disk):** remove the `disk:` block and set `plan: free`, then set
  `STORAGE_BACKEND=s3` with S3/R2 credentials so files persist in object storage. The free
  web plan sleeps after inactivity (slow first request) — not recommended for "always-on".
- **DB schema:** created on startup (`create_all`) plus additive column migrations
  (`ensure_columns`). Boolean defaults use `DEFAULT FALSE` for Postgres compatibility.
- **Secrets:** never commit real keys. `ANTHROPIC_API_KEY` and the admin credentials are
  entered only in the Render dashboard; `SECRET_KEY` is auto-generated by Render.
