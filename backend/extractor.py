import requests
from urllib.parse import urlparse
from readability import Document
from bs4 import BeautifulSoup


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
    html_content = response.text
    
    # Extract domain from URL
    parsed = urlparse(url)
    domain = parsed.netloc
    if domain.startswith("www."):
        domain = domain[4:]
    
    # Parse with BeautifulSoup using html5lib (more lenient than lxml)
    soup = BeautifulSoup(html_content, 'html5lib')
    
    # Get title
    title = _extract_title(soup)
    
    # Use readability on the html5lib-parsed document
    doc = Document(str(soup))
    content = doc.summary()
    
    # If readability fails to extract content, use the body
    if not content or len(content) < 100:
        body = soup.find('body')
        if body:
            content = str(body)
        else:
            content = html_content
    
    return {
        "title": title,
        "content": content,
        "url": url,
        "domain": domain
    }


def _extract_title(soup) -> str:
    """Extract title from parsed HTML."""
    # Try various title sources
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    
    h1 = soup.find('h1')
    if h1 and h1.get_text():
        return h1.get_text().strip()
    
    # Try Open Graph title
    og_title = soup.find('meta', property='og:title')
    if og_title and og_title.get('content'):
        return og_title['content'].strip()
    
    return "Untitled"
