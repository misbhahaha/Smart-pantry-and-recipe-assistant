# Deploy: Render (API) + Streamlit Cloud (UI)

## Live URLs (this project)

| Role | URL |
|------|-----|
| **App (share this)** | https://smart-pantry-and-recipe-assistant-c6jnsjedabfmbrga9afsbx.streamlit.app |
| **API** | https://smart-pantry-and-recipe-assistant-1.onrender.com |
| **API health check** | https://smart-pantry-and-recipe-assistant-1.onrender.com/health |

Do **not** commit `PANTRY_SECRET` or `.env` — set those only in Render and Streamlit dashboards.

## What each URL is for

| URL | What you see | Who uses it |
|-----|----------------|-------------|
| `https://….onrender.com` | JSON API (`/health`, `/docs`) | **Not** the main app screen |
| `https://….streamlit.app` | Smart Pantry UI | **Share this link** |

If only Render is deployed, opening the Render link in a browser is **not** the full app.

## Render (API)

1. **Build command:** `pip install -r requirements-render.txt` (not `requirements.txt`)
2. **Start command:** `cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. **Environment:** **`PYTHON_VERSION=3.11.9`** (required — default 3.14 breaks regex at import), `PANTRY_SECRET=<secret>`
4. After Streamlit exists: `CORS_ORIGINS=https://your-app.streamlit.app`
5. Test: `https://YOUR-API.onrender.com/health` → `{"status":"ok"}` (or `/live` for a quick ping with no DB check)
6. If the URL **hangs** with no JSON: open **Render → Logs**. The process is not listening — usually wrong build (`requirements.txt` instead of `requirements-render.txt`), wrong start command, or a crash on boot. Redeploy after fixing.

**Render environment (recommended):**

| Variable | Example |
|----------|---------|
| `PYTHON_VERSION` | `3.11.9` |
| `PANTRY_SECRET` | long random string (same as Streamlit) |
| `CORS_ORIGINS` | `https://your-app.streamlit.app` |
| `AUTO_DISH_IMAGE_BACKFILL` | `0` (on free tier) |
| `AUTO_THEMEALDB_IMAGE_SEARCH` | `0` (on free tier) |
| `AUTO_THEMEALDB_ENRICH` | `0` (no bulk network import on boot) |
| `AUTO_KASHMIRI_THEMEALDB` | `0` |
| `SMART_PANTRY_BLOCKING_SEED` | `0` |

## Streamlit Cloud (UI)

1. [share.streamlit.io](https://share.streamlit.io) → repo → `frontend/streamlit/Home.py`
2. Secrets:

```toml
BACKEND_URL = "https://YOUR-API.onrender.com"
PUBLIC_APP_URL = "https://YOUR-APP.streamlit.app"
PANTRY_SECRET = "same-as-render"
CORS_ORIGINS = "https://YOUR-APP.streamlit.app"
```

3. Open the `.streamlit.app` URL on phone/laptop.

## Sign-in problems

| Symptom | Fix |
|---------|-----|
| “Cannot reach the API” / timeout | Set `BACKEND_URL` to your **current** Render URL; open `…/health` in a browser until you see `{"status":"ok"}`. |
| “404 (not found)” on sign-in | Old Render URL in secrets — copy the new URL from Render → **Settings** → copy service URL. **Reboot** Streamlit. |
| “Invalid credentials” with your usual password | Cloud DB is **new and empty**. Use **Create account** (same email is fine if not taken). |
| Logged in briefly then kicked out | `PANTRY_SECRET` must match on Render and Streamlit exactly. |
