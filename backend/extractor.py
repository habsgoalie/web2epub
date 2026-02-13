import requests
from urllib.parse import urlparse
from readability import Document


def extract_article(url: str) -> dict:
    """
    Fetch a URL and extract the article content (title + clean HTML body).
    
    Returns:
        {
            "title": str,
            "content": str,
            "url": str,
            "domain": str
        }
    
    Raises:
        requests.RequestException: If network request fails
        Exception: If extraction fails
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        )
    }
    
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    
    doc = Document(response.text)
    title = doc.short_title() or doc.title() or "Untitled"
    content = doc.summary()
    
    # Extract domain from URL
    parsed = urlparse(url)
    domain = parsed.netloc
    if domain.startswith("www."):
        domain = domain[4:]
    
    return {
        "title": title,
        "content": content,
        "url": url,
        "domain": domain
    }
