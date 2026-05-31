# Smart Pantry — separated frontend & backend

## Live app

| | URL |
|---|-----|
| **Open the app** | https://smart-pantry-and-recipe-assistant-c6jnsjedabfmbrga9afsbx.streamlit.app |
| **API (health)** | https://smart-pantry-and-recipe-assistant-1.onrender.com/health |

Deploy notes: [docs/DEPLOY-RENDER-STREAMLIT.md](docs/DEPLOY-RENDER-STREAMLIT.md)

## Layout

```text
project/
├── backend/                 # Python API only (FastAPI)
│   └── app/
│       ├── main.py          # Uvicorn entry: `app.main:app`
│       ├── core/            # config, database session, security (tokens, passwords)
│       ├── models/          # SQLAlchemy ORM
│       ├── schemas/         # Pydantic request/response models
│       ├── api/
│       │   ├── deps.py      # Auth: Bearer token → current user
│       │   └── v1/
│       │       ├── router.py
│       │       └── endpoints/   # auth, users, pantry, recipes, recommendations, imports, shopping, …
│       └── services/        # Business logic: AI recs, TheMealDB, TF‑IDF, substitutions, seed, scheduler, …
├── frontend/
│   └── streamlit/           # UI only; calls backend over HTTP
│       ├── Home.py
│       ├── lib/
│       │   └── api_client.py
│       └── pages/
├── data/
│   ├── catalog/             # Offline recipe JSON per cuisine
│   ├── datasets/            # Bundled dish photos (TheMealDB + catalog name map)
│   └── …                    # SQLite DB, sample CSVs
└── docker-compose.yml       # Optional MySQL
```

- **Backend** exposes JSON at `http://127.0.0.1:8000/api/v1/...` (see `/docs` for OpenAPI).
- **Frontend** is Streamlit; it defaults to that same host/port. Override with `BACKEND_URL` if needed.

## Project objectives (feature map)

| Objective | Where in the app |
|-----------|------------------|
| Digital inventory management | **Ingredients** — structured pantry (name, qty, unit, category, expiry, notes) |
| Food waste reduction | **Dashboard** + expiry alerts; background scheduler; quantity tracking |
| Intelligent recipe recommendations | **Home** + **Recipes**; `/api/v1/recommendations/ai` and `/rules` |
| Health & nutrition support | **Profile** — diet/health tags, calorie target, daily log; recipes filtered by profile |
| Smart item entry | **Ingredients** — manual, barcode scan, Open Food Facts, label OCR |
| Cuisine-based discovery | **Recipes** by cuisine; substitution groups + per-recipe swap hints |
| Dish photos (trusted sources) | Curated + TheMealDB maps in `data/datasets/`; applied on API seed; run `python scripts/apply_curated_images.py` after catalog changes |
| Collaborative family planning | Register with **invite code**; shared household pantry (**Profile** shows code) |
| Automated grocery assistance | **Shopping** — grocery list from recipe missing ingredients (`/api/v1/shopping`) |

## Run

**Recommended (one command, from repo root):** starts the API, waits until it responds, then opens Streamlit.

```bash
python run_pantryflow.py
```

Optional: `API_PORT=8001 python run_pantryflow.py`, or `PANTRYFLOW_RELOAD=true` for `uvicorn --reload`.

### Browser URL (one link for all users)

The web UI is a normal **Streamlit** app: **one HTTPS or HTTP URL** opens in **Chrome, Safari, Firefox, and Edge** — no separate links per browser.

- **`run_pantryflow.py`** pins Streamlit to port **8501** and sets **`PUBLIC_APP_URL=http://127.0.0.1:8501`** unless you already exported **`PUBLIC_APP_URL`**. The home page and sidebar show that link for bookmarking/sharing.
- **Production:** deploy Streamlit (e.g. [Streamlit Community Cloud](https://streamlit.io/cloud)), then set **`PUBLIC_APP_URL`** to your public URL (e.g. `https://your-app.streamlit.app`) in the host’s environment or secrets so the UI displays the correct link. See [`.env.example`](.env.example).

**Advanced — two terminals:** start `uvicorn` in `backend/` on port **8000**, then:

```bash
export PUBLIC_APP_URL=http://127.0.0.1:8501
streamlit run frontend/streamlit/Home.py --server.port 8501
```

(same default **`BACKEND_URL`** as in the main **Run** section.)

### Phones and tablets

The web UI runs in **any modern mobile browser** (Safari, Chrome). Deploy Streamlit + API with public HTTPS URLs, or on the same Wi‑Fi use `http://YOUR-PC-IP:8501` and set **`BACKEND_URL`** to `http://YOUR-PC-IP:8000` (API must listen on `0.0.0.0`).

**Avoid starting the API twice.** `python run_pantryflow.py` already launches Uvicorn when nothing is listening on **`API_PORT`** (default **8000**). If you also run `uvicorn ... --port 8000` in another terminal, the second process fails with **address already in use**. Either use **only** `run_pantryflow.py`, or stop the other server first. If something else grabbed the port, free it (`lsof -nP -iTCP:8000 -sTCP:LISTEN`) or run with **`API_PORT=8001`** (and point Streamlit at that port via **`BACKEND_URL`**).

Environment:

- `DATABASE_URL` — default SQLite in `data/pantry.db`; for MySQL use `mysql+pymysql://user:pass@host:3306/dbname`
- `OPENAI_API_KEY` — enables LLM reranking on `/api/v1/recommendations/ai`
- `PANTRY_SECRET` — signing key for access tokens
- `CORS_ORIGINS` — comma-separated allowed origins (default includes Streamlit on port 8501)

## AI recommendations

- **`GET /api/v1/recommendations/ai`** — combines ingredient overlap + substitutions + TF‑IDF similarity; if `OPENAI_API_KEY` is set, top candidates are reranked with short reasons via the Chat Completions API.
- **`GET /api/v1/recommendations/rules`** — same pantry logic without any LLM.

## External data

- **TheMealDB** — `GET /api/v1/imports/themealdb/areas`, `POST /api/v1/imports/themealdb` with `{"area":"Italian","limit":15}`.
- **Open Food Facts** — used when adding pantry items from a barcode (`POST /api/v1/pantry/from-openfoodfacts`).
- **CSV** — `POST /api/v1/imports/recipes-csv` (Kaggle-style columns documented in `backend/app/services/kaggle_loader.py`).









