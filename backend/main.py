import os
import sys
import hashlib
from datetime import datetime
from typing import Annotated, Optional

import storage
import extractor
import pdf_generator
from fastapi import FastAPI, Depends, HTTPException, Request, Query, Response, Cookie, Form
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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

# Generate a session token from credentials (stable across restarts)
SESSION_TOKEN = hashlib.sha256(f"{AUTH_USERNAME}:{AUTH_PASSWORD}".encode()).hexdigest()


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

# HTTP Basic Auth (for API / extension)
security = HTTPBasic(auto_error=False)


def verify_basic_auth(credentials: Optional[HTTPBasicCredentials]) -> bool:
    """Check HTTP Basic Auth credentials."""
    if not credentials:
        return False
    username_match = secrets.compare_digest(credentials.username, AUTH_USERNAME)
    password_match = secrets.compare_digest(credentials.password, AUTH_PASSWORD)
    return username_match and password_match


def verify_session_cookie(session: Optional[str]) -> bool:
    """Check session cookie."""
    if not session:
        return False
    return secrets.compare_digest(session, SESSION_TOKEN)


async def require_auth_browser(
    request: Request,
    session: Annotated[Optional[str], Cookie()] = None,
):
    """Auth dependency for browser routes. Redirects to /login if not authenticated."""
    if not verify_session_cookie(session):
        raise HTTPException(status_code=302, headers={"Location": "/login"})


async def require_auth_api(
    credentials: Annotated[Optional[HTTPBasicCredentials], Depends(security)],
):
    """Auth dependency for API routes. Returns 401 if not authenticated."""
    if not verify_basic_auth(credentials):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


# Startup: ensure directories
@app.on_event("startup")
async def startup():
    storage.ensure_dirs()


# Template setup
template_dir = os.path.join(os.path.dirname(__file__), "templates")
jinja_env = Environment(loader=FileSystemLoader(template_dir))


# --- Login routes (no auth required) ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(session: Annotated[Optional[str], Cookie()] = None, error: str = ""):
    """Show login form. Redirect to / if already logged in."""
    if verify_session_cookie(session):
        return RedirectResponse(url="/", status_code=302)
    template = jinja_env.get_template("login.html")
    return HTMLResponse(content=template.render(error=error))


@app.post("/login")
async def login_submit(
    username: str = Form(...),
    password: str = Form(...),
):
    """Handle login form submission."""
    username_match = secrets.compare_digest(username, AUTH_USERNAME)
    password_match = secrets.compare_digest(password, AUTH_PASSWORD)

    if not (username_match and password_match):
        template = jinja_env.get_template("login.html")
        return HTMLResponse(
            content=template.render(error="Invalid username or password"),
            status_code=401,
        )

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="session",
        value=SESSION_TOKEN,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 365,  # 1 year
    )
    return response


@app.get("/logout")
async def logout():
    """Clear session cookie and redirect to login."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key="session")
    return response


# --- Browser routes (cookie auth) ---

@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    session: Annotated[Optional[str], Cookie()] = None,
    page: int = Query(1, ge=1),
):
    """Serve the HTML article list page (e-reader friendly)."""
    if not verify_session_cookie(session):
        return RedirectResponse(url="/login", status_code=302)

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
        has_next=page < total_pages,
    )

    return HTMLResponse(content=html)


@app.get("/articles/{article_id}/download")
async def download_article(
    article_id: str,
    session: Annotated[Optional[str], Cookie()] = None,
):
    """Serve the PDF file for an article (cookie auth for e-reader browser)."""
    if not verify_session_cookie(session):
        return RedirectResponse(url="/login", status_code=302)

    pdf_path = storage.get_pdf_path(article_id)
    if not pdf_path or not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Article not found")

    article = storage.get_article(article_id)
    title = article["title"] if article else "article"

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"{title[:50]}.pdf",
        headers={"Content-Disposition": f'attachment; filename="{title[:50]}.pdf"'},
    )


# --- API routes (HTTP Basic Auth for extension) ---

@app.post("/api/articles", status_code=201, dependencies=[Depends(require_auth_api)])
async def create_article(request: Request):
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
            url=extracted["url"],
        )

        # Save to storage
        article = storage.add_article(
            title=extracted["title"],
            url=extracted["url"],
            domain=extracted["domain"],
            pdf_bytes=pdf_bytes,
        )

        return article

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to process article: {str(e)}"
        )


@app.get("/api/articles", dependencies=[Depends(require_auth_api)])
async def list_articles():
    """Return JSON list of all saved articles, sorted by newest first."""
    articles = storage.load_articles()
    articles.sort(key=lambda a: a["saved_at"], reverse=True)
    return articles


@app.delete(
    "/api/articles/{article_id}",
    status_code=204,
    dependencies=[Depends(require_auth_api)],
)
async def delete_article(article_id: str):
    """Delete an article and its PDF."""
    found = storage.delete_article(article_id)
    if not found:
        raise HTTPException(status_code=404, detail="Article not found")
    return None
