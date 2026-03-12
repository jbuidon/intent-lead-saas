# 🎯 AI Buyer Intent Lead Finder

A SaaS tool that scans the web for people actively looking to hire services — powered by OpenAI and SerpAPI.

## Features

- 🔍 Enter any keyword → AI finds buyer-intent posts
- 🤖 GPT-4o-mini scores each post from 1–10 for buyer intent
- 📊 Dashboard shows leads with intent scores and links
- 🔄 Background scanner runs every hour, storing leads automatically
- 📅 `/daily-leads` endpoint returns all stored leads

---

## Project Structure

```
intent-lead-saas/
├── backend/          → FastAPI app (deploy to Render)
│   ├── main.py
│   ├── search_engine.py
│   ├── extractor.py
│   ├── intent_ai.py
│   ├── scanner.py
│   ├── database.py
│   ├── requirements.txt
│   └── render.yaml
│
├── frontend/         → Static HTML/JS UI (deploy to Vercel)
│   ├── index.html
│   ├── app.js
│   └── package.json
│
└── README.md
```

---

## Setup & Deploy

### 1. Get API Keys

You need **two** API keys:

| Key | Where to get it | Cost |
|-----|----------------|------|
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) | Pay per use (~$0.001/request) |
| `SERP_API_KEY` | [serpapi.com](https://serpapi.com) | 100 free searches/month |

---

### 2. Deploy Backend to Render

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → **New Web Service**
3. Connect your GitHub repo
4. Set **Root Directory** to `backend`
5. Build command: `pip install -r requirements.txt`
6. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
7. Add environment variables:
   - `OPENAI_API_KEY` = your key
   - `SERP_API_KEY` = your key
8. Deploy → you'll get a URL like `https://intent-lead-engine.onrender.com`

> ⚠️ **Free tier note:** Render free instances sleep after 15 minutes of inactivity. The first request after sleep takes ~30 seconds to respond.

---

### 3. Deploy Frontend to Vercel

1. Open `frontend/app.js`
2. Replace `YOUR_RENDER_BACKEND_URL` with your actual Render URL
3. Go to [vercel.com](https://vercel.com) → **New Project**
4. Import your GitHub repo
5. Set **Root Directory** to `frontend`
6. Deploy

---

### 4. Configure Tracked Keywords (Scanner)

Edit `backend/scanner.py` and update the `TRACKED_KEYWORDS` list:

```python
TRACKED_KEYWORDS = [
    "seo agency",
    "ai receptionist",
    "roof repair",
    "your service here",
]
```

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Health check |
| `GET /search?keyword=seo+agency` | Search for buyer intent leads |
| `GET /daily-leads` | Return all stored leads from DB |

---

## ⚠️ Important Notes

- **SQLite on Render free tier**: Data resets on each redeploy. For persistent storage, use [Supabase](https://supabase.com) (free PostgreSQL) and swap SQLite for `psycopg2`.
- **SerpAPI free tier**: 100 searches/month. Each `/search` call runs ~25 queries. Upgrade for production use.
- **CORS**: Currently set to `allow_origins=["*"]`. In production, replace with your Vercel URL.
