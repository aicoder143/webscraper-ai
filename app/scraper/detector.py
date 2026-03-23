import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}

def detect_rendering_mode(url: str) -> str:
    """
    Returns: 'api' | 'http' | 'playwright'
    Detects what kind of scraping the site needs.
    """
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS)
        soup = BeautifulSoup(resp.text, 'lxml')
        body_text = soup.body.get_text(strip=True) if soup.body else ''
        script_tags = soup.find_all('script')

        has_react    = any('react' in str(s).lower() or '__NEXT_DATA__' in str(s) for s in script_tags)
        has_vue      = any('vue' in str(s).lower() for s in script_tags)
        has_angular  = any('ng-version' in str(s).lower() for s in script_tags)
        is_empty     = len(body_text) < 200

        # Check for WordPress REST API
        wp_check = requests.get(
            url.rstrip('/') + '/wp-json/wp/v2/posts',
            timeout=5, headers=HEADERS
        )
        if wp_check.status_code == 200:
            return 'api'

        if is_empty or has_react or has_vue or has_angular:
            return 'playwright'

        return 'http'

    except Exception:
        return 'http'
