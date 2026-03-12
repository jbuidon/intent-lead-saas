from contextlib import asynccontextmanager
import threading
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
import json

load_dotenv()

from search_engine import build_queries, search_web
from extractor import extract_leads
from intent_ai import score_intent
from database import save_lead, get_all_leads
from scanner import run_scanner
from facebook import scan_group


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
    return {"status": "LeadRadar API Running", "version": "3.0"}


@app.get("/search")
def search_stream(
    keyword:      str = Query(...),
    provider:     str = Query("openai"),
    provider_key: str = Query(""),
    serp_key:     str = Query(""),
):
    """
    Streaming search endpoint — sends each lead as it's found using
    Server-Sent Events (SSE). This lets the frontend show leads in real time
    AND lets the user stop the search at any point without wasting credits
    on queries that haven't run yet.
    """
    if not keyword.strip():
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")

    valid_providers = ("openai", "gemini", "claude")
    if provider not in valid_providers:
        raise HTTPException(status_code=400, detail=f"Provider must be one of: {valid_providers}")

    def event_stream():
        queries = build_queries(keyword)
        total_queries = len(queries)

        # Send initial progress event
        yield f"data: {json.dumps({'type': 'progress', 'current': 0, 'total': total_queries})}\n\n"

        for i, query in enumerate(queries):
            try:
                results  = search_web(query, serp_key_override=serp_key)
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
                        # Stream this lead to the frontend immediately
                        yield f"data: {json.dumps({'type': 'lead', 'data': e})}\n\n"

            except Exception as ex:
                print(f"Error on query '{query}': {ex}")
                # Send error event but keep going
                yield f"data: {json.dumps({'type': 'error', 'message': str(ex)})}\n\n"

            # Send progress update after each query
            yield f"data: {json.dumps({'type': 'progress', 'current': i + 1, 'total': total_queries})}\n\n"

        # Signal completion
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Disable Nginx buffering on Render
        },
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
    """
    Scan one or more Facebook groups for buyer-intent posts.
    Body: { group_urls: [...], fb_token: "...", provider: "openai", provider_key: "..." }
    """
    group_urls   = body.get("group_urls", [])
    fb_token     = body.get("fb_token", "").strip()
    provider     = body.get("provider", "openai")
    provider_key = body.get("provider_key", "")

    if not group_urls:
        raise HTTPException(status_code=400, detail="No group URLs provided")
    if not fb_token:
        raise HTTPException(status_code=400, detail="Facebook access token is required")

    results = []
    for url in group_urls:
        result = scan_group(
            group_url=url,
            token=fb_token,
            provider=provider,
            provider_key=provider_key,
        )
        results.append(result)

    return results


# ── NEW PLATFORM ENDPOINTS ────────────────────────────────────────────────────
from platforms import scan_facebook_page, scan_instagram, score_linkedin_paste


@app.post("/facebook/scan-page")
def facebook_scan_page(body: dict):
    """
    Scan Facebook Pages for buyer-intent posts and interested commenters.
    Body: { page_urls: [...], fb_token, provider, provider_key }
    """
    page_urls    = body.get("page_urls", [])
    fb_token     = body.get("fb_token", "").strip()
    provider     = body.get("provider", "openai")
    provider_key = body.get("provider_key", "")

    if not page_urls:
        raise HTTPException(status_code=400, detail="No page URLs provided")
    if not fb_token:
        raise HTTPException(status_code=400, detail="Facebook access token required")

    return [
        scan_facebook_page(url, fb_token, provider, provider_key)
        for url in page_urls
    ]


@app.post("/instagram/scan")
def instagram_scan(body: dict):
    """
    Scan Instagram accounts linked to this Facebook token for interested commenters.
    Body: { fb_token, provider, provider_key }
    """
    fb_token     = body.get("fb_token", "").strip()
    provider     = body.get("provider", "openai")
    provider_key = body.get("provider_key", "")

    if not fb_token:
        raise HTTPException(status_code=400, detail="Facebook/Instagram access token required")

    return scan_instagram(fb_token, provider, provider_key)


@app.post("/linkedin/score")
def linkedin_score(body: dict):
    """
    Score manually pasted LinkedIn content (posts, comments, profile bios).
    Body: { items: [{text, url, person_name, content_type}], provider, provider_key }
    """
    items        = body.get("items", [])
    provider     = body.get("provider", "openai")
    provider_key = body.get("provider_key", "")

    if not items:
        raise HTTPException(status_code=400, detail="No items provided")

    return score_linkedin_paste(items, provider, provider_key)
