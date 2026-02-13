import requests
from urllib.parse import urlparse
import trafilatura
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
    
    # Try to get title from HTML first
    title = _extract_title(html_content)
    
    # Use trafilatura to extract article content
    try:
        result = trafilatura.extract(
            html_content,
            url=url,
            output_format='html',
            include_comments=False,
            include_tables=False,
            include_images=True,
            include_links=False
        )
        
        if not result:
            # Fallback: use the full HTML body
            soup = BeautifulSoup(html_content, 'html.parser')
            body = soup.find('body')
            result = str(body) if body else html_content
            
    except Exception as e:
        # Fallback on any extraction error
        print(f"Trafilatura extraction failed: {e}")
        soup = BeautifulSoup(html_content, 'html.parser')
        body = soup.find('body')
        result = str(body) if body else html_content
    
    return {
        "title": title,
        "content": result,
        "url": url,
        "domain": domain
    }


def _extract_title(html_content: str) -> str:
    """Extract title from HTML."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
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
            
    except Exception:
        pass
    
    return "Untitled"
