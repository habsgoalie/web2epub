import os
import sys
from datetime import datetime
from typing import Annotated

import storage
import extractor
import pdf_generator
from fastapi import FastAPI, Depends, HTTPException, Request, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from jinja2 import Environment, FileSystemLoader
import secrets


# Environment variables
AUTH_USERNAME = os.environ.get("AUTH_USERNAME")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD")

# Validate required env vars
if not AUTH_USERNAME or not AUTH_PASSWORD:
    print("ERROR: AUTH_USERNAME and AUTH_PASSWORD environment variables must be set", file=sys.stderr)
    sys.exit(1)


# Create FastAPI app
app = FastAPI(title="web2epub", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth
security = HTTPBasic()


def verify_credentials(credentials: Annotated[HTTPBasicCredentials, Depends(security)]):
    """Verify HTTP Basic Auth credentials against environment variables."""
    username_match = secrets.compare_digest(credentials.username, AUTH_USERNAME)
    password_match = secrets.compare_digest(credentials.password, AUTH_PASSWORD)
    
    if not (username_match and password_match):
        raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Basic"})
    
    return credentials


# Startup: ensure directories
@app.on_event("startup")
async def startup():
    storage.ensure_dirs()


# Template setup
template_dir = os.path.join(os.path.dirname(__file__), "templates")
jinja_env = Environment(loader=FileSystemLoader(template_dir))


# HTML Response helper
@app.get("/", response_class=HTMLResponse)
async def index(
    page: int = Query(1, ge=1),
    credentials: Annotated[HTTPBasicCredentials, Depends(verify_credentials)]
):
    """Serve the HTML article list page (e-reader friendly)."""
    articles = storage.load_articles()
    
    # Sort by saved_at descending (newest first)
    articles.sort(key=lambda a: a["saved_at"], reverse=True)
    
    # Pagination
    per_page = 20
    total = len(articles)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    
    start = (page - 1) * per_page
    end = start + per_page
    page_articles = articles[start:end]
    
    # Format dates nicely
    for article in page_articles:
        saved_at = datetime.fromisoformat(article["saved_at"])
        article["formatted_date"] = saved_at.strftime("%b %d, %Y")
    
    template = jinja_env.get_template("index.html")
    html = template.render(
        articles=page_articles,
        page=page,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages
    )
    
    return HTMLResponse(content=html)


# API Routes

@app.post("/api/articles", status_code=201)
async def create_article(
    request: Request,
    credentials: Annotated[HTTPBasicCredentials, Depends(verify_credentials)]
):
    """Save a new article: fetch URL, extract content, generate PDF, store."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON body")
    
    url = body.get("url")
    if not url or not isinstance(url, str):
        raise HTTPException(status_code=422, detail="URL is required")
    
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="Invalid URL scheme")
    
    try:
        # Extract article
        extracted = extractor.extract_article(url)
        
        # Generate PDF
        pdf_bytes = pdf_generator.generate_pdf(
            title=extracted["title"],
            content=extracted["content"],
            url=extracted["url"]
        )
        
        # Save to storage
        article = storage.add_article(
            title=extracted["title"],
            url=extracted["url"],
            domain=extracted["domain"],
            pdf_bytes=pdf_bytes
        )
        
        return article
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process article: {str(e)}")


@app.get("/api/articles")
async def list_articles(
    credentials: Annotated[HTTPBasicCredentials, Depends(verify_credentials)]
):
    """Return JSON list of all saved articles, sorted by newest first."""
    articles = storage.load_articles()
    articles.sort(key=lambda a: a["saved_at"], reverse=True)
    return articles


@app.delete("/api/articles/{article_id}", status_code=204)
async def delete_article(
    article_id: str,
    credentials: Annotated[HTTPBasicCredentials, Depends(verify_credentials)]
):
    """Delete an article and its PDF."""
    found = storage.delete_article(article_id)
    if not found:
        raise HTTPException(status_code=404, detail="Article not found")
    return None


@app.get("/articles/{article_id}/download")
async def download_article(
    article_id: str,
    credentials: Annotated[HTTPBasicCredentials, Depends(verify_credentials)]
):
    """Serve the PDF file for an article."""
    pdf_path = storage.get_pdf_path(article_id)
    if not pdf_path or not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Article not found")
    
    article = storage.get_article(article_id)
    title = article["title"] if article else "article"
    
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"{title[:50]}.pdf",
        headers={"Content-Disposition": f'attachment; filename="{title[:50]}.pdf"'}
    )
