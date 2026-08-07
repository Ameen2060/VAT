# Deployment Guide — Vercel (frontend) + Render (backend)

The app is two deployables:

| Piece | Host | URL (target) |
|-------|------|--------------|
| Next.js dashboard (`apps/web`) | **Vercel** | `https://keturah-vat.vercel.app` |
| FastAPI API + OCR (`apps/api`) | **Render** (Docker) | `https://keturah-vat-api.onrender.com` |
| PostgreSQL | Render managed DB | (internal) |
| Uploaded files + PDF reports | Render persistent disk `/var/data` | (internal) |

> The backend can't run on Vercel — it needs OCR models, PyMuPDF, and a persistent
> filesystem/DB, which serverless doesn't provide. That's why it lives on Render.

> ⚠️ **Security note:** authentication/RBAC is not finished yet. Once this is on a
> public URL, anyone with the link can upload and read invoices. For real client
> data, finish Phase 4 (login) before sharing the URL, or keep it private.

---

## 1 — Push the repo to GitHub

Both Render and Vercel deploy from a Git repo.

```bash
cd <this folder>
git init && git add . && git commit -m "VAT compliance platform"
gh repo create keturah-vat --private --source . --push   # or create it on github.com
```

## 2 — Backend on Render (from the blueprint)

1. Render Dashboard → **New → Blueprint** → connect the GitHub repo.
2. Render reads [`render.yaml`](../render.yaml) and proposes:
   - web service **keturah-vat-api** (Docker, `apps/api/Dockerfile`) with a 1 GB disk at `/var/data`
   - PostgreSQL **keturah-vat-db**
3. Click **Apply**. First build takes a few minutes (installs OCR deps).
4. When live, note the URL, e.g. `https://keturah-vat-api.onrender.com`.
5. **Set the AI key:** service → **Environment** → add `ANTHROPIC_API_KEY` = your key → save (redeploys). Without it, the app still runs (deterministic engine + offline analysis); with it, you get full Claude analysis.
6. **Seed the knowledge base once:**
   ```bash
   curl -X POST https://keturah-vat-api.onrender.com/api/knowledge/seed
   ```
7. Verify: open `https://keturah-vat-api.onrender.com/health` → `{"status":"ok"}` and `/api/ai/status`.

**Free-tier variant (no disk):** remove the `disk:` block and set `plan: free` in
`render.yaml`, then set `STORAGE_BACKEND=s3` with `S3_ENDPOINT_URL / S3_ACCESS_KEY /
S3_SECRET_KEY / S3_BUCKET` (AWS S3 or Cloudflare R2). Files then persist in object
storage instead of the disk.

## 3 — Frontend on Vercel

1. Vercel → **Add New → Project** → import the same repo.
2. **Root Directory: `apps/web`** (important — it's a monorepo). Framework auto-detects as Next.js.
3. **Environment Variables** → add:
   | Name | Value |
   |------|-------|
   | `NEXT_PUBLIC_API_BASE` | `https://keturah-vat-api.onrender.com` |
4. **Project name `keturah-vat`** → gives `https://keturah-vat.vercel.app` (if the name is free).
5. Deploy.

## 4 — Connect the two (CORS)

The backend only accepts browser calls from allow-listed origins. `render.yaml` already
sets `API_CORS_ORIGINS=https://keturah-vat.vercel.app`. If your Vercel URL differs,
update that env var on Render (comma-separate multiple origins) and redeploy.

## 5 — Smoke test

1. Open `https://keturah-vat.vercel.app`.
2. Go to **Document Analysis**, upload an invoice → confirm extraction, verification
   items, validation checks, and the compliance verdict appear.
3. Generate a PDF report and download it.

---

## Notes & limitations

- **DB migrations:** the app creates tables on startup (`create_all`) plus a small
  additive column migration. For ongoing schema changes, add Alembic (Phase 4).
- **Cold starts:** Render Starter keeps the service warm; the free plan sleeps after
  inactivity (first request is slow).
- **Secrets:** never commit real keys. `ANTHROPIC_API_KEY` and `SECRET_KEY` are set in
  the Render dashboard (the blueprint marks them secret / auto-generated).
- **Custom domain:** to use your own domain later, add it in Vercel (frontend) and set
  `API_CORS_ORIGINS` on Render to match.
