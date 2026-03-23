import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def detect_changes(site, old_pages, new_pages) -> list:
    """
    Compare old vs new scraped pages.
    Returns list of change dicts.
    """
    changes = []

    old_urls = {p.page_url: p for p in old_pages}
    new_urls = {p.page_url: p for p in new_pages}

    # New pages found
    added = set(new_urls.keys()) - set(old_urls.keys())
    if added:
        changes.append({
            "change_type": "new_pages",
            "description": f"{len(added)} new pages discovered",
            "old_value":   str(len(old_urls)),
            "new_value":   str(len(new_urls)),
        })
        logger.info(f"[{site.url}] {len(added)} new pages found")

    # Pages removed
    removed = set(old_urls.keys()) - set(new_urls.keys())
    if removed:
        changes.append({
            "change_type": "removed_pages",
            "description": f"{len(removed)} pages no longer found",
            "old_value":   "\n".join(list(removed)[:10]),
            "new_value":   "",
        })
        logger.info(f"[{site.url}] {len(removed)} pages removed")

    # Word count change
    old_words = sum(p.word_count for p in old_pages)
    new_words = sum(p.word_count for p in new_pages)
    diff      = new_words - old_words
    pct       = abs(diff / old_words * 100) if old_words > 0 else 0

    if pct >= 10:
        direction = "increased" if diff > 0 else "decreased"
        changes.append({
            "change_type": "word_count",
            "description": (
                f"Total word count {direction} by "
                f"{abs(diff):,} words ({pct:.1f}%)"
            ),
            "old_value": str(old_words),
            "new_value": str(new_words),
        })
        logger.info(
            f"[{site.url}] Word count changed "
            f"{old_words:,} -> {new_words:,}"
        )

    # Content changes on existing pages
    changed_pages = []
    for url, new_page in new_urls.items():
        if url not in old_urls:
            continue
        old_page  = old_urls[url]
        old_words = old_page.word_count
        new_words = new_page.word_count
        if old_words == 0:
            continue
        page_pct = abs(new_words - old_words) / old_words * 100
        if page_pct >= 20:
            changed_pages.append({
                "url":      url,
                "old":      old_words,
                "new":      new_words,
                "pct":      round(page_pct, 1),
            })

    if changed_pages:
        desc = f"{len(changed_pages)} pages had significant content changes"
        details = "\n".join(
            f"{c['url'][:60]}: {c['old']}w -> {c['new']}w ({c['pct']}%)"
            for c in changed_pages[:5]
        )
        changes.append({
            "change_type": "content_change",
            "description": desc,
            "old_value":   details,
            "new_value":   str(len(changed_pages)),
        })
        logger.info(
            f"[{site.url}] {len(changed_pages)} pages changed"
        )

    return changes


def save_changes(site, changes: list):
    """Save detected changes to the database."""
    from .models import ContentChange
    saved = []
    for c in changes:
        obj = ContentChange.objects.create(
            site        = site,
            change_type = c["change_type"],
            description = c["description"],
            old_value   = c.get("old_value", ""),
            new_value   = c.get("new_value", ""),
        )
        saved.append(obj)
    return saved
