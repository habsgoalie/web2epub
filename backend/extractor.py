import requests
from urllib.parse import urlparse
from newspaper import Article
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
    # Extract domain from URL
    parsed = urlparse(url)
    domain = parsed.netloc
    if domain.startswith("www."):
        domain = domain[4:]
    
    # Use newspaper3k for extraction
    article = Article(url)
    article.download()
    article.parse()
    
    if not article.text:
        raise Exception("Could not extract article content from this URL")
    
    # Get title
    title = article.title if article.title else "Untitled"
    
    # Convert plain text to simple HTML
    # newspaper3k gives us clean text, wrap in HTML
    content_html = f"<div class='article-content'>{article.text.replace(chr(10), '<br>')}</div>"
    
    return {
        "title": title,
        "content": content_html,
        "url": url,
        "domain": domain
    }
