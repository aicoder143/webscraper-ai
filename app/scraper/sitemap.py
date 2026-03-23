import requests
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}


def get_base_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def fetch_robots_txt(base_url: str) -> dict:
    """
    Parse robots.txt and extract sitemap locations
    and disallowed paths.
    """
    result = {'sitemaps': [], 'disallowed': []}
    try:
        robots_url = base_url.rstrip('/') + '/robots.txt'
        resp = requests.get(robots_url, timeout=10, headers=HEADERS)
        if resp.status_code != 200:
            return result

        for line in resp.text.splitlines():
            line = line.strip()
            if line.lower().startswith('sitemap:'):
                sitemap_url = line.split(':', 1)[1].strip()
                result['sitemaps'].append(sitemap_url)
            elif line.lower().startswith('disallow:'):
                path = line.split(':', 1)[1].strip()
                if path:
                    result['disallowed'].append(path)

        logger.info(f"robots.txt found {len(result['sitemaps'])} sitemaps")
    except Exception as e:
        logger.warning(f"Could not fetch robots.txt: {e}")

    return result


def parse_sitemap_xml(sitemap_url: str, depth: int = 0) -> list:
    """
    Recursively parse sitemap XML.
    Handles both sitemap index files and URL sitemaps.
    Returns list of page URLs.
    """
    if depth > 3:
        return []

    urls = []
    try:
        resp = requests.get(sitemap_url, timeout=15, headers=HEADERS)
        if resp.status_code != 200:
            return urls

        root = ET.fromstring(resp.content)
        ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

        # Check if this is a sitemap index
        sitemaps = root.findall('sm:sitemap', ns)
        if sitemaps:
            # Sitemap index — recurse into each child sitemap
            for sitemap in sitemaps:
                loc = sitemap.find('sm:loc', ns)
                if loc is not None and loc.text:
                    child_urls = parse_sitemap_xml(loc.text.strip(), depth + 1)
                    urls.extend(child_urls)
        else:
            # Regular sitemap — extract URLs
            url_elements = root.findall('sm:url', ns)
            for url_el in url_elements:
                loc = url_el.find('sm:loc', ns)
                priority = url_el.find('sm:priority', ns)
                if loc is not None and loc.text:
                    urls.append({
                        'url': loc.text.strip(),
                        'priority': float(priority.text) if priority is not None else 0.5
                    })

        logger.info(f"Sitemap {sitemap_url} yielded {len(urls)} URLs")

    except ET.ParseError:
        logger.warning(f"Could not parse XML from {sitemap_url}")
    except Exception as e:
        logger.warning(f"Error fetching sitemap {sitemap_url}: {e}")

    return urls


def crawl_links(base_url: str, max_pages: int = 50) -> list:
    """
    Fallback crawler when no sitemap exists.
    Recursively follows internal links up to max_pages.
    """
    from bs4 import BeautifulSoup
    visited = set()
    to_visit = [base_url]
    found_urls = []
    base_domain = urlparse(base_url).netloc

    while to_visit and len(found_urls) < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            resp = requests.get(url, timeout=10, headers=HEADERS)
            if resp.status_code != 200:
                continue

            found_urls.append({'url': url, 'priority': 0.5})
            soup = BeautifulSoup(resp.text, 'lxml')

            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                full_url = urljoin(url, href)
                parsed = urlparse(full_url)

                # Only follow internal links
                if parsed.netloc == base_domain and full_url not in visited:
                    # Skip common non-content URLs
                    skip_exts = ('.pdf', '.jpg', '.png', '.gif', '.zip',
                                 '.css', '.js', '.xml', '.ico')
                    if not parsed.path.endswith(skip_exts):
                        to_visit.append(full_url)

        except Exception as e:
            logger.warning(f"Error crawling {url}: {e}")
            continue

    logger.info(f"Link crawl found {len(found_urls)} URLs")
    return found_urls


def discover_urls(url: str, max_pages: int = 50) -> dict:
    """
    Main entry point. Given any URL, returns:
    {
        'base_url': str,
        'urls': [{'url': str, 'priority': float}],
        'source': 'sitemap' | 'crawl',
        'disallowed': [str]
    }
    """
    base_url = get_base_url(url)
    logger.info(f"Starting discovery for {base_url}")

    # Step 1 — check robots.txt
    robots = fetch_robots_txt(base_url)
    disallowed = robots.get('disallowed', [])

    # Step 2 — try sitemaps from robots.txt
    all_urls = []
    sitemap_sources = robots.get('sitemaps', [])

    # Step 3 — also try common sitemap locations
    common_sitemaps = [
        base_url.rstrip('/') + '/sitemap.xml',
        base_url.rstrip('/') + '/sitemap_index.xml',
        base_url.rstrip('/') + '/sitemap/sitemap.xml',
    ]
    for sm in common_sitemaps:
        if sm not in sitemap_sources:
            sitemap_sources.append(sm)

    # Step 4 — parse all discovered sitemaps
    for sitemap_url in sitemap_sources:
        urls = parse_sitemap_xml(sitemap_url)
        all_urls.extend(urls)

    # Deduplicate
    seen = set()
    unique_urls = []
    for item in all_urls:
        if item['url'] not in seen:
            seen.add(item['url'])
            unique_urls.append(item)

    # Step 5 — fallback to link crawl if no sitemap found
    source = 'sitemap'
    if not unique_urls:
        logger.info("No sitemap found, falling back to link crawl")
        unique_urls = crawl_links(base_url, max_pages)
        source = 'crawl'

    # Sort by priority (highest first) and limit
    unique_urls.sort(key=lambda x: x.get('priority', 0.5), reverse=True)
    unique_urls = unique_urls[:max_pages]

    return {
        'base_url': base_url,
        'urls': unique_urls,
        'source': source,
        'disallowed': disallowed,
        'total_found': len(unique_urls)
    }
