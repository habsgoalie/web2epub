import re
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup


def _is_twitter_url(url: str) -> bool:
    """Check if the URL is a Twitter/X post."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host not in ("twitter.com", "x.com"):
        return False
    # Match /<user>/status/<id> pattern
    return bool(re.match(r"^/[^/]+/status/\d+", parsed.path))


def _resolve_tco(url: str) -> str:
    """Resolve a t.co shortened URL to its destination."""
    try:
        resp = requests.head(url, allow_redirects=True, timeout=10)
        return resp.url
    except Exception:
        return url


def _tweet_is_link_only(soup) -> str | None:
    """If tweet content is just a single t.co link, return that URL. Otherwise None."""
    paragraphs = soup.find_all("p")
    if len(paragraphs) != 1:
        return None
    p = paragraphs[0]
    links = p.find_all("a")
    text_without_links = p.get_text(strip=True)
    # Check if the only text content is the link text itself
    if len(links) == 1:
        link_text = links[0].get_text(strip=True)
        href = links[0].get("href", "")
        if text_without_links == link_text and "t.co" in href:
            return href
    return None


def _extract_twitter(url: str) -> dict:
    """Extract tweet content using Twitter's oEmbed API."""
    oembed_url = "https://publish.twitter.com/oembed"
    resp = requests.get(
        oembed_url,
        params={"url": url, "omit_script": "true"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    author = data.get("author_name", "Unknown")
    html = data.get("html", "")

    # Parse the oEmbed blockquote to extract tweet text paragraphs
    soup = BeautifulSoup(html, "html.parser")

    # If the tweet is just a shared link, resolve it and extract that article instead
    tco_link = _tweet_is_link_only(soup)
    if tco_link:
        resolved_url = _resolve_tco(tco_link)
        # If it resolves to a non-Twitter page, extract that article
        if not _is_twitter_url(resolved_url):
            resolved_parsed = urlparse(resolved_url)
            resolved_host = resolved_parsed.netloc.lower().removeprefix("www.")
            if resolved_host not in ("twitter.com", "x.com", "t.co"):
                return extract_article(resolved_url)

        # Otherwise fall through and render the tweet with the resolved link
        resolved_url = resolved_url if resolved_url != tco_link else tco_link
        parsed = urlparse(url)
        domain = parsed.netloc.lower().removeprefix("www.")
        return {
            "title": f"@{author} shared: {resolved_url[:70]}",
            "content": (
                f'<p style="font-size: 12pt; color: #555;">Post by '
                f'<strong>{author}</strong></p>'
                f'<p>Shared link: <a href="{resolved_url}">{resolved_url}</a></p>'
                f'<p style="font-size: 10pt; color: #888; margin-top: 2em;">'
                f'<a href="{url}">View original post</a></p>'
            ),
            "url": url,
            "domain": domain,
        }

    # Extract just the <p> tags (the actual tweet text)
    paragraphs = soup.find_all("p")
    tweet_paragraphs = []
    for p in paragraphs:
        text = p.get_text(strip=True)
        if text:
            tweet_paragraphs.append(str(p))

    tweet_text = soup.get_text(separator=" ", strip=True)
    title = f"@{author}: {tweet_text[:80]}{'...' if len(tweet_text) > 80 else ''}"

    # Build clean, readable HTML content for the PDF
    content_parts = []
    content_parts.append(f'<p style="font-size: 12pt; color: #555;">Post by '
                         f'<strong>{author}</strong></p>')
    if tweet_paragraphs:
        for p_html in tweet_paragraphs:
            content_parts.append(p_html)
    else:
        # Fallback: use full blockquote text
        content_parts.append(f"<p>{tweet_text}</p>")

    content_parts.append(f'<p style="font-size: 10pt; color: #888; margin-top: 2em;">'
                         f'<a href="{url}">View original post</a></p>')

    content = "\n".join(content_parts)

    parsed = urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")

    return {
        "title": title,
        "content": content,
        "url": url,
        "domain": domain,
    }


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
    # Handle Twitter/X posts via oEmbed API
    if _is_twitter_url(url):
        return _extract_twitter(url)

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
