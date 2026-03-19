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
from database import save_lead, get_all_leads, save_keywords, get_keywords
from scanner import run_scanner, scanner_state
from facebook import scan_group, get_group_posts, extract_group_id
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
    return {"status": "LeadRadar API Running", "version": "4.2"}


@app.get("/search")
def search_stream(
    keyword:      str   = Query(...),
    provider:     str   = Query("openai"),
    provider_key: str   = Query(""),
    serp_key:     str   = Query(""),
    min_score:    float = Query(6.0),
    fb_token:     str   = Query(""),       # Facebook token (optional)
    group_urls:   str   = Query(""),       # Comma-separated group URLs (optional)
):
    """
    Streaming SSE search.
    Sources: Reddit API → RSS → DuckDuckGo → Facebook (DDG) → SerpAPI fallback.
    If fb_token + group_urls are provided, also scans your Facebook groups for the keyword.
    min_score: only return leads scoring at or above this threshold (default 6).
    """
    if not keyword.strip():
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")

    valid_providers = ("openai", "gemini", "claude")
    if provider not in valid_providers:
        raise HTTPException(status_code=400, detail=f"Provider must be one of: {valid_providers}")

    min_score = max(1.0, min(10.0, min_score))

    # Parse group URLs from comma-separated string
    parsed_group_urls = [u.strip() for u in group_urls.split(",") if u.strip()] if group_urls else []
    include_fb_groups = bool(fb_token.strip() and parsed_group_urls)

    def event_stream():
        # ── STEP 1: Web search ────────────────────────────────────────────
        yield f"data: {json.dumps({'type': 'progress', 'current': 0, 'total': 1, 'message': 'Gathering results from Reddit, RSS, DuckDuckGo, Facebook…'})}\n\n"

        try:
            all_results = multi_search(keyword, serp_key=serp_key)
            total = len(all_results)

            if total == 0 and not include_fb_groups:
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            if total > 0:
                _msg2 = f'Scoring {total} web results with AI (min score: {min_score})...'
                yield f"data: {json.dumps({'type': 'progress', 'current': 0, 'total': total, 'message': _msg2})}\n\n"

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
                                e["post_date"]     = result.get("post_date", "")
                                e["created_at"]    = result.get("post_date", "")
                                save_lead(e["post_text"], e["post_url"], score, post_date=result.get("post_date", ""))
                                yield f"data: {json.dumps({'type': 'lead', 'data': e})}\n\n"

                    except Exception as ex:
                        print(f"Error scoring result {i}: {ex}")
                        continue

                    yield f"data: {json.dumps({'type': 'progress', 'current': i + 1, 'total': total})}\n\n"

        except Exception as ex:
            yield f"data: {json.dumps({'type': 'error', 'message': str(ex)})}\n\n"

        # ── STEP 2: Facebook Groups search ───────────────────────────────
        if include_fb_groups:
            _msg3 = f'Scanning {len(parsed_group_urls)} Facebook group(s) for keyword: {keyword}...'
            yield f"data: {json.dumps({'type': 'progress', 'current': 0, 'total': len(parsed_group_urls), 'message': _msg3})}\n\n"

            for gi, group_url in enumerate(parsed_group_urls):
                try:
                    group_id = extract_group_id(group_url)

                    # Fetch posts from this group
                    posts = get_group_posts(group_id, fb_token.strip(), limit=50)

                    # Filter posts that contain the keyword
                    keyword_lower = keyword.lower()
                    matching_posts = [
                        p for p in posts
                        if keyword_lower in (p.get("message") or p.get("story") or "").lower()
                        or any(
                            keyword_lower in (c.get("message") or "").lower()
                            for c in p.get("comments", {}).get("data", [])
                        )
                    ]

                    _msg = f'Found {len(matching_posts)} posts mentioning "{keyword}" in group {gi+1}...'
                    yield f"data: {json.dumps({'type': 'progress', 'current': gi, 'total': len(parsed_group_urls), 'message': _msg})}\n\n"

                    for post in matching_posts:
                        post_text = post.get("message") or post.get("story") or ""
                        if not post_text or len(post_text.strip()) < 15:
                            continue

                        post_url    = post.get("permalink_url") or f"https://facebook.com/{post.get('id','')}"
                        post_author = post.get("from") or {}
                        author_id   = post_author.get("id", "unknown")
                        author_name = post_author.get("name", "Unknown")
                        profile_url = f"https://www.facebook.com/profile.php?id={author_id}" if author_id != "unknown" else "https://www.facebook.com"

                        try:
                            score = score_intent(post_text, provider=provider, api_key_override=provider_key)
                        except Exception as ex:
                            print(f"FB scoring error: {ex}")
                            score = 0.0

                        if score >= min_score:
                            lead = {
                                "post_text":    post_text[:400],
                                "post_url":     post_url,
                                "intent_score": score,
                                "source_name":  "facebook_group",
                                "name":         author_name,
                                "profile_url":  profile_url,
                                "lead_type":    "post_author",
                            }
                            save_lead(post_text, post_url, score)
                            yield f"data: {json.dumps({'type': 'lead', 'data': lead})}\n\n"

                        # Also check comments mentioning the keyword
                        for comment in post.get("comments", {}).get("data", []):
                            comment_text = comment.get("message", "").strip()
                            if keyword_lower not in comment_text.lower():
                                continue
                            if not comment_text or len(comment_text) < 5:
                                continue

                            commenter      = comment.get("from") or {}
                            commenter_id   = commenter.get("id", "unknown")
                            commenter_name = commenter.get("name", "Unknown")
                            commenter_profile = f"https://www.facebook.com/profile.php?id={commenter_id}" if commenter_id != "unknown" else "https://www.facebook.com"

                            combined_text = f"Original post: {post_text[:200]}\n\nComment: {comment_text}"

                            try:
                                comment_score = score_intent(combined_text, provider=provider, api_key_override=provider_key)
                            except Exception as ex:
                                print(f"FB comment scoring error: {ex}")
                                comment_score = 0.0

                            if comment_score >= min_score:
                                lead = {
                                    "post_text":    f'💬 "{comment_text}"',
                                    "post_url":     post_url,
                                    "intent_score": comment_score,
                                    "source_name":  "facebook_group",
                                    "name":         commenter_name,
                                    "profile_url":  commenter_profile,
                                    "lead_type":    "commenter",
                                }
                                save_lead(comment_text, post_url, comment_score)
                                yield f"data: {json.dumps({'type': 'lead', 'data': lead})}\n\n"

                except PermissionError as ex:
                    _err1 = 'FB Group permission error: ' + str(ex)
                    yield f"data: {json.dumps({'type': 'error', 'message': _err1})}\n\n"
                except Exception as ex:
                    _err2 = 'FB Group error: ' + str(ex)
                    yield f"data: {json.dumps({'type': 'error', 'message': _err2})}\n\n"

                yield f"data: {json.dumps({'type': 'progress', 'current': gi + 1, 'total': len(parsed_group_urls)})}\n\n"

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
        {
            "id": r[0],
            "post": r[1],
            "url": r[2],
            "intent": r[3],
            "created_at": r[4],
            "keyword": r[5] if len(r) > 5 else "",
            "post_date": r[6] if len(r) > 6 else "",
        }
        for r in rows
    ]


@app.post("/keywords")
def update_keywords(body: dict):
    """Save tracked keywords from frontend Settings so scanner picks them up."""
    keywords = body.get("keywords", [])
    if not isinstance(keywords, list):
        raise HTTPException(status_code=400, detail="keywords must be a list")
    save_keywords([k.strip() for k in keywords if k.strip()])
    return {"saved": len(keywords)}


@app.get("/keywords")
def fetch_keywords():
    return {"keywords": get_keywords()}


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


@app.get("/scanner/status")
def get_scanner_status():
    """Return current background scanner state (last run, next run, keywords)."""
    return scanner_state


@app.get("/facebook/my-groups")
def facebook_my_groups(fb_token: str = Query(...)):
    """Fetch all Facebook groups the token owner is a member of."""
    import requests as req
    if not fb_token.strip():
        raise HTTPException(status_code=400, detail="fb_token is required")
    try:
        r = req.get(
            "https://graph.facebook.com/v19.0/me/groups",
            params={"fields": "id,name,member_count", "access_token": fb_token.strip(), "limit": 100},
            timeout=10,
        )
        if r.status_code == 403:
            raise HTTPException(status_code=403, detail="Token lacks groups_access_member_info permission")
        r.raise_for_status()
        return r.json().get("data", [])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
