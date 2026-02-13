import requests
from urllib.parse import urlparse
import trafilatura


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
    
    # Use trafilatura to extract article
    result = trafilatura.extract(
        response.text,
        url=url,
        output_format='html',
        include_comments=False,
        include_tables=False,
        include_images=True,
        include_links=False
    )
    
    if not result:
        raise Exception("Could not extract article content from this URL")
    
    # Get title
    metadata = trafilatura.extract_metadata(response.text)
    title = metadata.title if metadata and hasattr(metadata, 'title') and metadata.title else "Untitled"
    
    # Extract domain from URL
    parsed = urlparse(url)
    domain = parsed.netloc
    if domain.startswith("www."):
        domain = domain[4:]
    
    return {
        "title": title,
        "content": result,
        "url": url,
        "domain": domain
    }
