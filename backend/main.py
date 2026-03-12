from contextlib import asynccontextmanager
import threading
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
import json

load_dotenv()

from sources import multi_search
from extractor import extract_leads
from intent_ai import score_intent
from database import save_lead, get_all_leads
from scanner import run_scanner
from facebook import scan_group
from platforms import scan_facebook_page, scan_instagram, score_linkedin_paste


@asynccontextmanager
async def lifespan(app: FastAPI):
    thread = threading.Thread(target=run_scanner, daemon=True)
    thread.start()
    yield


app = FastAPI(title="LeadRadar API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"status": "LeadRadar API Running", "version": "4.1"}


@app.get("/search")
def search_stream(
    keyword:      str   = Query(...),
    provider:     str   = Query("openai"),
    provider_key: str   = Query(""),
    serp_key:     str   = Query(""),
    min_score:    float = Query(6.0),   # frontend can pass 1-10, default 6
):
    """
    Streaming SSE search.
    Sources: Reddit API → RSS → DuckDuckGo → Facebook (DDG) → SerpAPI fallback.
    min_score: only return leads scoring at or above this threshold (default 6).
    """
    if not keyword.strip():
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")

    valid_providers = ("openai", "gemini", "claude")
    if provider not in valid_providers:
        raise HTTPException(status_code=400, detail=f"Provider must be one of: {valid_providers}")

    # Clamp min_score to reasonable range
    min_score = max(1.0, min(10.0, min_score))

    def event_stream():
        yield f"data: {json.dumps({'type': 'progress', 'current': 0, 'total': 1, 'message': 'Gathering results from Reddit, RSS, DuckDuckGo, Facebook…'})}\n\n"

        try:
            all_results = multi_search(keyword, serp_key=serp_key)
            total = len(all_results)

            if total == 0:
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            yield f"data: {json.dumps({'type': 'progress', 'current': 0, 'total': total, 'message': f'Scoring {total} results with AI (min score: {min_score})…'})}\n\n"

            for i, result in enumerate(all_results):
                try:
                    extracted = extract_leads([{
                        "snippet": result.get("snippet", ""),
                        "link":    result.get("link", ""),
                        "title":   result.get("title", ""),
                    }])

                    for e in extracted:
                        score = score_intent(
                            e["post_text"],
                            provider=provider,
                            api_key_override=provider_key,
                        )
                        if score >= min_score:
                            e["intent_score"]  = score
                            e["source_name"]   = result.get("source_name", "web")
                            save_lead(e["post_text"], e["post_url"], score)
                            yield f"data: {json.dumps({'type': 'lead', 'data': e})}\n\n"

                except Exception as ex:
                    print(f"Error scoring result {i}: {ex}")
                    continue

                yield f"data: {json.dumps({'type': 'progress', 'current': i + 1, 'total': total})}\n\n"

        except Exception as ex:
            yield f"data: {json.dumps({'type': 'error', 'message': str(ex)})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/daily-leads")
def daily_leads():
    rows = get_all_leads()
    return [
        {"id": r[0], "post": r[1], "url": r[2], "intent": r[3], "created_at": r[4]}
        for r in rows
    ]


@app.post("/facebook/scan")
def facebook_scan(body: dict):
    group_urls   = body.get("group_urls", [])
    fb_token     = body.get("fb_token", "").strip()
    provider     = body.get("provider", "openai")
    provider_key = body.get("provider_key", "")
    if not group_urls: raise HTTPException(status_code=400, detail="No group URLs provided")
    if not fb_token:   raise HTTPException(status_code=400, detail="Facebook token required")
    return [scan_group(url, fb_token, provider, provider_key) for url in group_urls]


@app.post("/facebook/scan-page")
def facebook_scan_page(body: dict):
    page_urls    = body.get("page_urls", [])
    fb_token     = body.get("fb_token", "").strip()
    provider     = body.get("provider", "openai")
    provider_key = body.get("provider_key", "")
    if not page_urls: raise HTTPException(status_code=400, detail="No page URLs provided")
    if not fb_token:  raise HTTPException(status_code=400, detail="Facebook token required")
    return [scan_facebook_page(url, fb_token, provider, provider_key) for url in page_urls]


@app.post("/instagram/scan")
def instagram_scan(body: dict):
    fb_token     = body.get("fb_token", "").strip()
    provider     = body.get("provider", "openai")
    provider_key = body.get("provider_key", "")
    if not fb_token: raise HTTPException(status_code=400, detail="Token required")
    return scan_instagram(fb_token, provider, provider_key)


@app.post("/linkedin/score")
def linkedin_score(body: dict):
    items        = body.get("items", [])
    provider     = body.get("provider", "openai")
    provider_key = body.get("provider_key", "")
    if not items: raise HTTPException(status_code=400, detail="No items provided")
    return score_linkedin_paste(items, provider, provider_key)
