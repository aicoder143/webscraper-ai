import requests
import logging
from bs4 import BeautifulSoup
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}


def extract_content(html: str) -> dict:
    """
    Extract clean text content from raw HTML.
    Uses BeautifulSoup only — no readability dependency.
    Removes script, style, nav, footer, header tags.
    Returns dict with title, content, headings, meta_description.
    """
    soup = BeautifulSoup(html, 'lxml')

    # Remove noise elements
    for tag in soup.find_all([
        'script', 'style', 'nav', 'footer',
        'header', 'aside', 'noscript', 'iframe',
        'form', 'button', 'svg', 'img'
    ]):
        tag.decompose()

    # Extract title
    title = ''
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Extract meta description
    meta_desc = ''
    meta = soup.find('meta', attrs={'name': 'description'})
    if meta:
        meta_desc = meta.get('content', '').strip()

    # Extract headings
    headings = []
    for tag in soup.find_all(['h1', 'h2', 'h3']):
        text = tag.get_text(strip=True)
        if text and len(text) > 2:
            headings.append({'level': tag.name, 'text': text[:200]})

    # Extract main content — try content areas first
    content = ''
    content_selectors = [
        'main', 'article', '[role="main"]',
        '.content', '.post-content', '.entry-content',
        '.article-body', '#content', '#main'
    ]
    for selector in content_selectors:
        el = soup.select_one(selector)
        if el:
            content = el.get_text(separator=' ', strip=True)
            break

    # Fallback to body
    if not content and soup.body:
        content = soup.body.get_text(separator=' ', strip=True)

    # Clean up whitespace
    import re
    content = re.sub(r'\s+', ' ', content).strip()

    # Calculate word count properly
    words = [w for w in content.split() if len(w) > 1]
    word_count = len(words)

    return {
        'title':            title,
        'content':          content,
        'meta_description': meta_desc,
        'headings':         headings,
        'word_count':       word_count,
    }


def scrape_page_http(url: str) -> dict:
    """
    Scrape a single page using plain HTTP.
    """
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS)
        resp.raise_for_status()

        extracted = extract_content(resp.text)

        logger.info(
            f"HTTP scraped {url} — "
            f"{extracted['word_count']} words"
        )

        return {
            'url':             url,
            'title':           extracted['title'],
            'content':         extracted['content'],
            'meta_description':extracted['meta_description'],
            'headings':        extracted['headings'],
            'word_count':      extracted['word_count'],
            'success':         True,
            'method':          'http',
        }

    except requests.exceptions.Timeout:
        logger.warning(f"Timeout: {url}")
        return {'url': url, 'success': False,
                'error': 'timeout', 'method': 'http',
                'word_count': 0, 'content': ''}

    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTP {e}: {url}")
        return {'url': url, 'success': False,
                'error': str(e), 'method': 'http',
                'word_count': 0, 'content': ''}

    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        return {'url': url, 'success': False,
                'error': str(e), 'method': 'http',
                'word_count': 0, 'content': ''}


def scrape_page_playwright(url: str) -> dict:
    """
    Scrape a JS-rendered page using Playwright.
    """
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                ]
            )
            context = browser.new_context(
                user_agent=HEADERS['User-Agent'],
                viewport={'width': 1280, 'height': 800}
            )
            page = context.new_page()

            # Block images/media to speed up
            page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in ['image', 'media', 'font']
                else route.continue_()
            )

            page.goto(url, wait_until='networkidle', timeout=30000)
            page.evaluate(
                "window.scrollTo(0, document.body.scrollHeight)"
            )
            page.wait_for_timeout(2000)

            html  = page.content()
            browser.close()

        extracted = extract_content(html)
        logger.info(
            f"Playwright scraped {url} — "
            f"{extracted['word_count']} words"
        )

        return {
            'url':             url,
            'title':           extracted['title'],
            'content':         extracted['content'],
            'meta_description':extracted['meta_description'],
            'headings':        extracted['headings'],
            'word_count':      extracted['word_count'],
            'success':         True,
            'method':          'playwright',
        }

    except Exception as e:
        logger.error(f"Playwright error {url}: {e}")
        # Fallback to HTTP
        logger.info(f"Falling back to HTTP for {url}")
        return scrape_page_http(url)


def scrape_page_api(url: str) -> dict:
    """
    Scrape WordPress REST API.
    """
    try:
        base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        api_url  = base_url.rstrip('/') + '/wp-json/wp/v2/posts?per_page=100'

        resp = requests.get(api_url, timeout=15, headers=HEADERS)
        resp.raise_for_status()
        posts = resp.json()

        parts = []
        for post in posts:
            title = post.get('title', {}).get('rendered', '')
            body  = BeautifulSoup(
                post.get('content', {}).get('rendered', ''),
                'lxml'
            ).get_text(separator=' ', strip=True)
            parts.append(f"{title}. {body}")

        content    = ' '.join(parts)
        word_count = len([w for w in content.split() if len(w) > 1])

        logger.info(f"API scraped {url} — {word_count} words")

        return {
            'url':             url,
            'title':           f'WordPress: {base_url}',
            'content':         content,
            'meta_description':'',
            'headings':        [],
            'word_count':      word_count,
            'success':         True,
            'method':          'api',
        }

    except Exception as e:
        logger.error(f"API error {url}: {e}")
        return scrape_page_http(url)


def scrape_page(url: str, mode: str = 'http') -> dict:
    """
    Main router — picks the right scraper based on mode.
    Always returns a dict with word_count key guaranteed.
    """
    logger.info(f"Scraping [{mode}] {url}")

    if mode == 'playwright':
        result = scrape_page_playwright(url)
    elif mode == 'api':
        result = scrape_page_api(url)
    else:
        result = scrape_page_http(url)

    # Guarantee word_count is always present and correct
    if 'content' in result and result.get('word_count', 0) == 0:
        content = result.get('content', '')
        result['word_count'] = len(
            [w for w in content.split() if len(w) > 1]
        )

    return result
