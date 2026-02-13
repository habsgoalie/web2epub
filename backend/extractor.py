import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup


def extract_article(url: str) -> dict:
    """
    Fetch a URL and extract the article content using BeautifulSoup.
    
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
    
    # Parse with BeautifulSoup using Python's built-in html.parser
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract domain from URL
    parsed = urlparse(url)
    domain = parsed.netloc
    if domain.startswith("www."):
        domain = domain[4:]
    
    # Get title
    title = _extract_title(soup)
    
    # Extract article content
    content = _extract_content(soup)
    
    if not content:
        raise Exception("Could not extract article content from this URL")
    
    return {
        "title": title,
        "content": content,
        "url": url,
        "domain": domain
    }


def _extract_title(soup) -> str:
    """Extract title from parsed HTML."""
    # Try title tag
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    
    # Try h1
    h1 = soup.find('h1')
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    
    # Try Open Graph
    og_title = soup.find('meta', property='og:title')
    if og_title and og_title.get('content'):
        return og_title['content'].strip()
    
    return "Untitled"


def _extract_content(soup) -> str:
    """Extract article content from parsed HTML."""
    # Remove script and style elements
    for script in soup(["script", "style", "nav", "header", "footer"]):
        script.decompose()
    
    # Try to find article or main content
    article = soup.find('article')
    if article:
        return str(article)
    
    main = soup.find('main')
    if main:
        return str(main)
    
    # Try common content containers
    for selector in ['div.content', 'div.post', 'div.entry', 'div.post-content', '.article-body']:
        elem = soup.select_one(selector)
        if elem:
            return str(elem)
    
    # Fallback to body
    body = soup.find('body')
    if body:
        return str(body)
    
    # Last resort: return all text
    return str(soup)
