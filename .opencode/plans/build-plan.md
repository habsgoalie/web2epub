# web2epub — Product Requirements Document & Build Plan

## Overview

A self-hosted "read it later" service (similar to Mozilla Pocket) that lets users save web articles via a Chrome browser extension. Articles are extracted, converted to PDF, and served on a minimal HTML page designed to be browsed from an e-reader (Kobo Libra) over Tailscale.

## Architecture

```
[Chrome Extension] --POST URL--> [FastAPI Backend] --extract & PDF--> [Filesystem]
                                       |
                                 [Simple HTML UI] <-- Kobo e-reader browser
```

## Technology Stack

| Component          | Technology                                      |
|--------------------|------------------------------------------------|
| Backend framework  | Python 3.12 + FastAPI                           |
| Article extraction | readability-lxml (same algo as Firefox Reader)  |
| PDF generation     | weasyprint (HTML-to-PDF)                        |
| HTML templating    | Jinja2 (server-rendered, no JS on frontend)     |
| HTTP client        | requests                                        |
| Auth               | HTTP Basic Auth (username/password from env)    |
| Storage            | Filesystem (JSON manifest + PDF files on disk)  |
| Deployment         | Docker + Docker Compose                         |
| Browser extension  | Chrome Manifest V3                              |
| Access             | Tailscale (private network)                     |

## File Structure

```
web2epub/
├── backend/
│   ├── main.py              # FastAPI app, routes, auth middleware
│   ├── extractor.py         # Article fetching & readability extraction
│   ├── pdf_generator.py     # Clean HTML-to-PDF via weasyprint
│   ├── storage.py           # JSON manifest + filesystem CRUD operations
│   ├── templates/
│   │   └── index.html       # E-reader-friendly article list page
│   └── requirements.txt     # Python dependencies
├── extension/
│   ├── manifest.json        # Chrome Manifest V3
│   ├── popup.html           # Extension popup UI (save button)
│   ├── popup.js             # Popup save logic
│   ├── options.html         # Extension settings page
│   ├── options.js           # Settings persistence logic
│   └── icons/               # Extension icons (16, 48, 128px)
├── Dockerfile               # Python slim + weasyprint system deps
├── docker-compose.yml       # Single service, volume mount, env vars
├── .dockerignore
└── .gitignore
```

Runtime data directory (mounted as Docker volume, NOT committed to git):
```
data/
├── articles.json            # [{id, title, url, domain, saved_at, filename}, ...]
└── pdfs/
    └── <uuid>.pdf           # Generated PDF files
```

---

## Detailed Component Specifications

### 1. `backend/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
jinja2==3.1.4
readability-lxml==0.8.1
weasyprint==62.3
requests==2.32.3
lxml==5.3.0
lxml_html_clean==0.2.2
```

### 2. `backend/storage.py` — JSON Manifest + Filesystem Operations

**Purpose:** CRUD operations on the article list. No database — uses a JSON file as the data store.

**Data model (each article):**
```python
{
    "id": str,          # UUID4
    "title": str,       # Extracted article title
    "url": str,         # Original source URL
    "domain": str,      # Extracted domain (e.g. "nytimes.com")
    "saved_at": str,    # ISO 8601 timestamp
    "filename": str     # PDF filename on disk (e.g. "<uuid>.pdf")
}
```

**Constants:**
- `DATA_DIR` — Path to data directory, default `./data`, configurable via `DATA_DIR` env var
- `ARTICLES_FILE` — `{DATA_DIR}/articles.json`
- `PDFS_DIR` — `{DATA_DIR}/pdfs`

**Functions:**
- `ensure_dirs()` — Create `DATA_DIR` and `PDFS_DIR` if they don't exist
- `load_articles() -> list[dict]` — Read and parse `articles.json`. Return empty list if file doesn't exist.
- `save_articles(articles: list[dict])` — Write article list to `articles.json` (atomic write: write to temp file then rename)
- `add_article(title, url, domain, pdf_bytes) -> dict` — Generate UUID, write PDF to `PDFS_DIR/<uuid>.pdf`, append to manifest, return the article dict
- `delete_article(article_id: str) -> bool` — Remove article from manifest and delete its PDF file. Return True if found.
- `get_article(article_id: str) -> dict | None` — Look up a single article by ID.
- `get_pdf_path(article_id: str) -> Path | None` — Return the full path to the PDF file for an article.

**Important:** Use file locking or atomic writes to avoid corruption if two saves happen concurrently.

### 3. `backend/extractor.py` — Article Extraction

**Purpose:** Fetch a URL and extract the article content (title + clean HTML body).

**Functions:**
- `extract_article(url: str) -> dict` — Fetches the URL with `requests.get()`, runs it through `readability-lxml`'s `Document` class, returns:
  ```python
  {
      "title": str,       # Article title
      "content": str,     # Clean HTML of the article body
      "url": str,         # Original URL
      "domain": str       # Parsed domain from URL
  }
  ```

**Details:**
- Set a reasonable User-Agent header (e.g. `Mozilla/5.0 ...`) to avoid blocks
- Set a timeout on the request (15 seconds)
- Extract domain from URL using `urllib.parse.urlparse`
- Raise meaningful exceptions on failure (network error, extraction failure)
- The `content` returned by readability is clean HTML suitable for PDF conversion

### 4. `backend/pdf_generator.py` — PDF Generation

**Purpose:** Convert extracted article HTML into a clean, readable PDF optimized for e-reader screens.

**Functions:**
- `generate_pdf(title: str, content: str, url: str) -> bytes` — Wraps the article content in a full HTML document with clean reading styles, converts to PDF via weasyprint, returns the PDF bytes.

**HTML template for the PDF (embedded in the function):**
```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {
            font-family: Georgia, serif;
            font-size: 14pt;
            line-height: 1.6;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            color: #222;
        }
        h1 { font-size: 20pt; margin-bottom: 0.3em; }
        .source { color: #666; font-size: 10pt; margin-bottom: 2em; }
        img { max-width: 100%; height: auto; }
        a { color: #222; }
        pre, code { font-size: 11pt; overflow-wrap: break-word; }
    </style>
</head>
<body>
    <h1>{title}</h1>
    <p class="source">{url}</p>
    {content}
</body>
</html>
```

**Details:**
- Use `weasyprint.HTML(string=html_string).write_pdf()` to generate the PDF
- Handle weasyprint warnings/errors gracefully
- Return raw bytes (caller writes to disk)

### 5. `backend/main.py` — FastAPI App, Routes, Auth

**Purpose:** The main application. Defines all API routes and serves the web UI.

**Environment variables:**
- `AUTH_USERNAME` — Required. Username for HTTP Basic Auth.
- `AUTH_PASSWORD` — Required. Password for HTTP Basic Auth.
- `DATA_DIR` — Optional. Path to data directory (default: `./data`).

**Auth:**
- Use FastAPI's `HTTPBasic` security scheme
- Create a dependency `verify_credentials(credentials: HTTPBasicCredentials)` that checks against env vars
- Use `secrets.compare_digest()` to avoid timing attacks
- Apply auth to ALL routes

**Routes:**

| Method   | Path                        | Description                                    |
|----------|-----------------------------|------------------------------------------------|
| `GET`    | `/`                         | Serve the HTML article list (e-reader UI)      |
| `POST`   | `/api/articles`             | Save a new article (accepts `{"url": "..."}`)  |
| `GET`    | `/api/articles`             | Return JSON list of all saved articles          |
| `DELETE` | `/api/articles/{id}`        | Delete an article and its PDF                   |
| `GET`    | `/articles/{id}/download`   | Serve the PDF file for download                 |

**Route details:**

`GET /` :
- Load articles from storage, sorted by `saved_at` descending (newest first)
- Implement simple pagination: `?page=1` query param, 20 articles per page
- Render `templates/index.html` with Jinja2

`POST /api/articles` :
- Accept JSON body: `{"url": "https://..."}`
- Call `extractor.extract_article(url)`
- Call `pdf_generator.generate_pdf(title, content, url)`
- Call `storage.add_article(title, url, domain, pdf_bytes)`
- Return `201` with the article metadata JSON
- Return `422` if URL is missing/invalid
- Return `500` with error message if extraction or PDF generation fails
- Add CORS headers (so the browser extension can call from any origin)

`GET /api/articles` :
- Return the full article list as JSON, sorted by `saved_at` descending

`DELETE /api/articles/{id}` :
- Call `storage.delete_article(id)`
- Return `204` on success, `404` if not found

`GET /articles/{id}/download` :
- Look up article, get PDF path from storage
- Return `FileResponse` with `Content-Disposition: attachment` and PDF mime type
- Return `404` if article not found

**Startup:**
- Call `storage.ensure_dirs()` on startup
- Validate that `AUTH_USERNAME` and `AUTH_PASSWORD` env vars are set (exit with error if not)

**CORS:**
- Add `CORSMiddleware` allowing all origins (needed for the browser extension to call the API from any page)

### 6. `backend/templates/index.html` — E-Reader Web UI

**Purpose:** A server-rendered HTML page optimized for e-reader browsers (no JavaScript).

**Design constraints:**
- NO JavaScript — Kobo's browser has poor/broken JS support
- High contrast (black text on white background)
- Large font sizes and tap targets (e-readers have imprecise touch)
- Simple semantic HTML
- Minimal CSS (inline in a `<style>` tag)
- Pagination via simple `?page=N` links

**Page content:**
- Header: "Saved Articles" title
- For each article: title (as link to PDF download), domain, date saved (formatted nicely, e.g. "Feb 12, 2026")
- Each article is a distinct block/row with clear separation
- Pagination links at the bottom: "Previous" / "Next"
- If no articles: "No saved articles yet." message

**Jinja2 template variables:**
- `articles` — list of article dicts for the current page
- `page` — current page number
- `total_pages` — total number of pages
- `has_prev` / `has_next` — booleans for pagination

**Styling guidelines:**
```css
body {
    font-family: serif;
    font-size: 18px;
    line-height: 1.5;
    max-width: 800px;
    margin: 0 auto;
    padding: 16px;
    background: #fff;
    color: #000;
}
h1 { font-size: 28px; border-bottom: 2px solid #000; padding-bottom: 8px; }
.article { border-bottom: 1px solid #ccc; padding: 16px 0; }
.article-title { font-size: 20px; font-weight: bold; }
.article-title a { color: #000; text-decoration: none; }
.article-meta { font-size: 14px; color: #555; margin-top: 4px; }
.pagination { margin-top: 24px; font-size: 18px; }
.pagination a { margin: 0 12px; padding: 8px 16px; border: 1px solid #000; text-decoration: none; color: #000; }
```

### 7. `Dockerfile`

```dockerfile
FROM python:3.12-slim

# Install weasyprint system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libcairo2 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 8. `docker-compose.yml`

```yaml
services:
  web2epub:
    build: .
    ports:
      - "${PORT:-8000}:8000"
    environment:
      - AUTH_USERNAME=${AUTH_USERNAME}
      - AUTH_PASSWORD=${AUTH_PASSWORD}
      - DATA_DIR=/data
    volumes:
      - ./data:/data
    restart: unless-stopped
```

### 9. Chrome Extension (`extension/`)

**`manifest.json`:**
```json
{
  "manifest_version": 3,
  "name": "web2epub Saver",
  "version": "1.0.0",
  "description": "Save articles to your web2epub server for reading on your e-reader",
  "permissions": ["activeTab", "storage"],
  "action": {
    "default_popup": "popup.html",
    "default_icon": {
      "16": "icons/icon16.png",
      "48": "icons/icon48.png",
      "128": "icons/icon128.png"
    }
  },
  "options_page": "options.html",
  "icons": {
    "16": "icons/icon16.png",
    "48": "icons/icon48.png",
    "128": "icons/icon128.png"
  }
}
```

**`popup.html`:**
- Simple popup with a "Save This Article" button
- Status area showing: "Saving...", "Saved!", or error message
- Styled simply, small fixed-width popup (~320px wide)
- If no server URL configured, show message linking to options page

**`popup.js`:**
- On button click:
  1. Get current tab's URL via `chrome.tabs.query`
  2. Load server URL and credentials from `chrome.storage.sync`
  3. Send `POST` to `{serverUrl}/api/articles` with `{"url": tabUrl}`
  4. Include `Authorization: Basic <base64(username:password)>` header
  5. Show success (article title) or error message in the popup
- On load: check if server URL is configured, show setup prompt if not

**`options.html`:**
- Form with three fields: Server URL, Username, Password
- "Save" button
- "Test Connection" button (calls `GET /api/articles` to verify)
- Status message area

**`options.js`:**
- Save settings to `chrome.storage.sync`
- Load settings on page open
- Test connection: `GET {serverUrl}/api/articles` with auth header, show success/failure

**Extension icons:**
- Generate simple SVG-based PNG icons at 16x16, 48x48, 128x128
- Simple design: a document/book icon or a bookmark icon
- Can use a simple solid-color geometric design

### 10. `.dockerignore`

```
.git
data
extension
*.md
.gitignore
```

### 11. `.gitignore`

```
data/
__pycache__/
*.pyc
.env
*.egg-info/
.venv/
```

---

## Build Order (for the implementing agent)

Execute these tasks in this exact order:

1. **`backend/requirements.txt`** — Write the dependencies file
2. **`backend/storage.py`** — Implement the storage layer (JSON manifest + filesystem)
3. **`backend/extractor.py`** — Implement article fetching and extraction
4. **`backend/pdf_generator.py`** — Implement PDF generation
5. **`backend/main.py`** — Implement the FastAPI app with all routes, auth, and CORS
6. **`backend/templates/index.html`** — Create the e-reader-friendly HTML template
7. **`Dockerfile`** — Create the Docker build file
8. **`docker-compose.yml`** — Create the compose configuration
9. **`extension/manifest.json`** — Chrome extension manifest
10. **`extension/popup.html` + `extension/popup.js`** — Extension popup
11. **`extension/options.html` + `extension/options.js`** — Extension options page
12. **`extension/icons/`** — Generate simple extension icons (create simple SVGs or placeholder PNGs)
13. **`.dockerignore`** — Docker ignore file
14. **`.gitignore`** — Git ignore file
15. **Test:** Run `docker compose build` to verify the Docker build succeeds
16. **Test:** Run `docker compose up` and verify the server starts and responds

---

## Acceptance Criteria

- [ ] `docker compose build` succeeds without errors
- [ ] `docker compose up` starts the server on port 8000
- [ ] `GET /` returns the HTML article list page (requires auth)
- [ ] `POST /api/articles` with `{"url": "https://example.com"}` extracts content and generates a PDF
- [ ] `GET /articles/{id}/download` serves the generated PDF
- [ ] The HTML page is readable and navigable on an e-reader browser (no JS required)
- [ ] The Chrome extension can be loaded as an unpacked extension
- [ ] The Chrome extension options page can save server URL and credentials
- [ ] The Chrome extension popup can save the current page's URL to the server
- [ ] All routes require HTTP Basic Auth
- [ ] CORS is configured to allow the extension to call from any origin
