from contextlib import asynccontextmanager
import threading
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from search_engine import build_queries, search_web
from extractor import extract_leads
from intent_ai import score_intent
from database import save_lead, get_all_leads
from scanner import run_scanner


@asynccontextmanager
async def lifespan(app: FastAPI):
    thread = threading.Thread(target=run_scanner, daemon=True)
    thread.start()
    yield


app = FastAPI(title="LeadRadar API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten to your Vercel URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"status": "LeadRadar API Running", "version": "2.0"}


@app.get("/search")
def search(
    keyword: str = Query(..., description="Service keyword to search"),
    provider: str = Query("openai", description="AI provider: openai | gemini | claude"),
    provider_key: str = Query("", description="API key for chosen AI provider (from frontend settings)"),
    serp_key: str = Query("", description="SerpAPI key (from frontend settings)"),
):
    """
    Search for buyer-intent posts.
    API keys can be passed per-request from the frontend Settings page,
    falling back to server environment variables if not provided.
    """
    if not keyword.strip():
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")

    valid_providers = ("openai", "gemini", "claude")
    if provider not in valid_providers:
        raise HTTPException(status_code=400, detail=f"Provider must be one of: {valid_providers}")

    queries = build_queries(keyword)
    leads = []

    for query in queries:
        try:
            # Pass the per-request serp_key so users don't need server env vars
            results = search_web(query, serp_key_override=serp_key)
            extracted = extract_leads(results)

            for e in extracted:
                score = score_intent(
                    e["post_text"],
                    provider=provider,
                    api_key_override=provider_key,
                )
                if score >= 7:
                    e["intent_score"] = score
                    save_lead(e["post_text"], e["post_url"], score)
                    leads.append(e)

        except Exception as ex:
            print(f"Error on query '{query}': {ex}")
            continue

    return leads


@app.get("/daily-leads")
def daily_leads():
    rows = get_all_leads()
    return [
        {"id": r[0], "post": r[1], "url": r[2], "intent": r[3], "created_at": r[4]}
        for r in rows
    ]
