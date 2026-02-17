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


def _parse_twitter_url(url: str) -> tuple[str, str]:
    """Extract username and status ID from a Twitter/X URL."""
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    # parts = [username, "status", id]
    return parts[0], parts[2]


def _article_blocks_to_html(article: dict, entity_map: dict) -> str:
    """Convert fxtwitter article content blocks to clean HTML."""
    html_parts = []
    blocks = article.get("content", {}).get("blocks", [])

    for block in blocks:
        text = block.get("text", "")
        block_type = block.get("type", "unstyled")
        entity_ranges = block.get("entityRanges", [])
        inline_styles = block.get("inlineStyleRanges", [])

        if not text:
            continue

        # Apply inline styles and entity links
        # Build a list of markup insertions sorted by offset
        insertions = []  # (offset, is_close, priority, tag)

        for style in inline_styles:
            offset = style["offset"]
            length = style["length"]
            style_name = style.get("style", "")
            if style_name == "Bold":
                insertions.append((offset, False, 0, "<strong>"))
                insertions.append((offset + length, True, 0, "</strong>"))
            elif style_name == "Italic":
                insertions.append((offset, False, 0, "<em>"))
                insertions.append((offset + length, True, 0, "</em>"))

        for er in entity_ranges:
            offset = er["offset"]
            length = er["length"]
            key = str(er["key"])
            entity = entity_map.get(key, {})
            entity_data = entity.get("data", {})
            link_url = entity_data.get("url", "")
            if link_url:
                insertions.append((offset, False, 1, f'<a href="{link_url}">'))
                insertions.append((offset + length, True, 1, "</a>"))

        # Sort: by offset, then closes before opens, then by priority
        insertions.sort(key=lambda x: (x[0], x[1], x[2]))

        # Build the text with markup
        result = []
        last_pos = 0
        for offset, _is_close, _prio, tag in insertions:
            if offset > last_pos:
                result.append(text[last_pos:offset])
            result.append(tag)
            last_pos = offset
        if last_pos < len(text):
            result.append(text[last_pos:])

        styled_text = "".join(result)

        # Wrap in appropriate HTML element
        if block_type == "header-one":
            html_parts.append(f"<h2>{styled_text}</h2>")
        elif block_type == "header-two":
            html_parts.append(f"<h3>{styled_text}</h3>")
        elif block_type == "header-three":
            html_parts.append(f"<h4>{styled_text}</h4>")
        elif block_type == "unordered-list-item":
            html_parts.append(f"<li>{styled_text}</li>")
        elif block_type == "ordered-list-item":
            html_parts.append(f"<li>{styled_text}</li>")
        elif block_type == "blockquote":
            html_parts.append(f"<blockquote><p>{styled_text}</p></blockquote>")
        else:
            html_parts.append(f"<p>{styled_text}</p>")

    # Wrap consecutive <li> items in <ul> or <ol>
    output = []
    in_list = False
    for part in html_parts:
        if part.startswith("<li>"):
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append(part)
        else:
            if in_list:
                output.append("</ul>")
                in_list = False
            output.append(part)
    if in_list:
        output.append("</ul>")

    return "\n".join(output)


def _extract_twitter(url: str) -> dict:
    """Extract tweet content using the fxtwitter API."""
    username, status_id = _parse_twitter_url(url)

    # Use fxtwitter API which provides full tweet + article data
    api_url = f"https://api.fxtwitter.com/{username}/status/{status_id}"
    resp = requests.get(api_url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    tweet = data.get("tweet", {})
    author = tweet.get("author", {}).get("name", "Unknown")
    author_handle = tweet.get("author", {}).get("screen_name", "")
    tweet_text = tweet.get("text", "")

    parsed = urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")

    # Check if this tweet contains an X Article
    article = tweet.get("article")
    if article:
        article_title = article.get("title", "Untitled")
        entity_map_list = article.get("content", {}).get("entityMap", [])
        # Convert entity map list to dict keyed by "key" field
        entity_map = {}
        for item in entity_map_list:
            key = str(item.get("key", ""))
            entity_map[key] = item.get("value", {})

        content = _article_blocks_to_html(article, entity_map)

        # Add attribution
        content = (
            f'<p style="font-size: 12pt; color: #555;">By '
            f'<strong>{author}</strong> (@{author_handle})</p>\n'
            + content
            + f'\n<p style="font-size: 10pt; color: #888; margin-top: 2em;">'
            f'<a href="{url}">View original post</a></p>'
        )

        return {
            "title": article_title,
            "content": content,
            "url": url,
            "domain": domain,
        }

    # Regular tweet (no article) — check if it's just a shared link
    if not tweet_text or tweet_text.startswith("https://t.co/"):
        # Try to resolve any t.co links in the tweet
        urls = re.findall(r"https?://t\.co/\w+", tweet_text or "")
        if urls:
            resolved_url = _resolve_tco(urls[0])
            resolved_parsed = urlparse(resolved_url)
            resolved_host = resolved_parsed.netloc.lower().removeprefix("www.")
            if resolved_host not in ("twitter.com", "x.com", "t.co"):
                return extract_article(resolved_url)

    # Regular tweet with text content
    title = f"@{author_handle}: {tweet_text[:80]}{'...' if len(tweet_text) > 80 else ''}"
    if not title or title == f"@{author_handle}: ":
        title = f"Post by @{author_handle}"

    content_parts = [
        f'<p style="font-size: 12pt; color: #555;">Post by '
        f'<strong>{author}</strong> (@{author_handle})</p>',
    ]

    if tweet_text:
        # Convert newlines to paragraphs
        for para in tweet_text.split("\n"):
            para = para.strip()
            if para:
                content_parts.append(f"<p>{para}</p>")

    content_parts.append(
        f'<p style="font-size: 10pt; color: #888; margin-top: 2em;">'
        f'<a href="{url}">View original post</a></p>'
    )

    return {
        "title": title,
        "content": "\n".join(content_parts),
        "url": url,
        "domain": domain,
    }


def _resolve_tco(url: str) -> str:
    """Resolve a t.co shortened URL to its destination."""
    try:
        resp = requests.head(url, allow_redirects=True, timeout=10)
        return resp.url
    except Exception:
        return url


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
    # Handle Twitter/X posts via fxtwitter API
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
