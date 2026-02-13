import os
import json
import fcntl
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
ARTICLES_FILE = DATA_DIR / "articles.json"
PDFS_DIR = DATA_DIR / "pdfs"


def ensure_dirs():
    """Create DATA_DIR and PDFS_DIR if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PDFS_DIR.mkdir(parents=True, exist_ok=True)


def _lock_file(f):
    """Acquire an exclusive lock on a file."""
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)


def _unlock_file(f):
    """Release the lock on a file."""
    fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def load_articles() -> list[dict]:
    """Read and parse articles.json. Return empty list if file doesn't exist."""
    if not ARTICLES_FILE.exists():
        return []
    
    with open(ARTICLES_FILE, "r") as f:
        _lock_file(f)
        try:
            content = f.read()
        finally:
            _unlock_file(f)
        
        if not content:
            return []
        return json.loads(content)


def save_articles(articles: list[dict]):
    """Write article list to articles.json atomically."""
    temp_file = ARTICLES_FILE.with_suffix(".tmp")
    
    with open(temp_file, "w") as f:
        _lock_file(f)
        try:
            json.dump(articles, f, indent=2)
        finally:
            _unlock_file(f)
    
    # Atomic rename
    temp_file.rename(ARTICLES_FILE)


def add_article(title: str, url: str, domain: str, pdf_bytes: bytes) -> dict:
    """Generate UUID, write PDF to disk, append to manifest, return article dict."""
    article_id = str(uuid.uuid4())
    filename = f"{article_id}.pdf"
    pdf_path = PDFS_DIR / filename
    
    # Write PDF to disk
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    
    # Create article record
    article = {
        "id": article_id,
        "title": title,
        "url": url,
        "domain": domain,
        "saved_at": datetime.now().isoformat(),
        "filename": filename
    }
    
    # Load, append, and save
    articles = load_articles()
    articles.append(article)
    save_articles(articles)
    
    return article


def delete_article(article_id: str) -> bool:
    """Remove article from manifest and delete its PDF. Return True if found."""
    articles = load_articles()
    
    article = next((a for a in articles if a["id"] == article_id), None)
    if not article:
        return False
    
    # Remove from list
    articles = [a for a in articles if a["id"] != article_id]
    save_articles(articles)
    
    # Delete PDF file
    pdf_path = PDFS_DIR / article["filename"]
    if pdf_path.exists():
        pdf_path.unlink()
    
    return True


def get_article(article_id: str) -> Optional[dict]:
    """Look up a single article by ID."""
    articles = load_articles()
    return next((a for a in articles if a["id"] == article_id), None)


def get_pdf_path(article_id: str) -> Optional[Path]:
    """Return the full path to the PDF file for an article."""
    article = get_article(article_id)
    if not article:
        return None
    return PDFS_DIR / article["filename"]
