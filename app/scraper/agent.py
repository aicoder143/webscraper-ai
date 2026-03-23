import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def extract_key_values(site, pages) -> dict:
    """
    Phase 5 — AI agent that reads scraped content
    and extracts structured key values.
    Works with or without an OpenAI API key.
    """
    openai_key = os.environ.get('OPENAI_API_KEY', '')

    if openai_key and openai_key != 'your-openai-key-here':
        return _extract_with_openai(site, pages, openai_key)
    else:
        logger.info("No OpenAI key — using rule-based extraction")
        return _extract_rule_based(site, pages)


def _build_context(site, pages, max_words: int = 3000) -> str:
    """
    Build condensed text context from all scraped pages.
    Simple chunking — no vector DB needed.
    """
    from urllib.parse import urlparse
    domain = urlparse(site.url).netloc
    parts  = [f"Website: {domain}", f"URL: {site.url}", "---"]
    words_used = 0

    # Sort by word count — most content-rich pages first
    sorted_pages = sorted(
        pages, key=lambda p: p.word_count, reverse=True
    )

    for page in sorted_pages:
        if not page.content or page.word_count == 0:
            continue
        if words_used >= max_words:
            break

        parts.append(f"\nPage: {page.title or page.page_url}")

        if page.meta_description:
            parts.append(f"Description: {page.meta_description}")

        if page.headings:
            headings_text = ' | '.join(
                h['text'] for h in page.headings[:4]
            )
            parts.append(f"Headings: {headings_text}")

        remaining = max_words - words_used
        words     = page.content.split()[:remaining]
        parts.append(' '.join(words))
        words_used += len(words)
        parts.append("---")

    return '\n'.join(parts)


def _extract_with_openai(site, pages, api_key: str) -> dict:
    """
    Use OpenAI GPT to extract structured key values.
    No vector DB — sends chunked text directly to GPT.
    """
    try:
        from openai import OpenAI
        client  = OpenAI(api_key=api_key)
        context = _build_context(site, pages, max_words=3000)

        prompt = f"""
Analyze this scraped website content and extract key information.
Return ONLY a valid JSON object with these exact keys:

{{
  "business_name": "company or site name",
  "business_type": "type of business/website",
  "description": "2-3 sentence description",
  "main_topics": ["topic1", "topic2", "topic3"],
  "products_services": ["item1", "item2"],
  "contact_email": "email if found, else null",
  "contact_phone": "phone if found, else null",
  "location": "city/country if found, else null",
  "social_links": ["url1", "url2"],
  "technologies": ["tech1", "tech2"],
  "key_facts": ["fact1", "fact2", "fact3"],
  "sentiment": "positive/neutral/negative",
  "language": "detected language",
  "total_pages_analyzed": {len(pages)}
}}

Website content:
{context}
"""
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a web content analyst. "
                        "Extract structured data. "
                        "Always respond with valid JSON only. "
                        "No markdown, no code fences."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=1000,
        )

        import json
        text   = response.choices[0].message.content.strip()
        text   = text.replace('```json','').replace('```','').strip()
        result = json.loads(text)
        result['extraction_method'] = 'openai-gpt'
        logger.info(f"OpenAI extraction complete for {site.url}")
        return result

    except Exception as e:
        logger.error(f"OpenAI extraction failed: {e}")
        return _extract_rule_based(site, pages)


def _extract_rule_based(site, pages) -> dict:
    """
    Rule-based extraction — no external API needed.
    Uses regex and frequency analysis.
    """
    import re
    from urllib.parse import urlparse
    from collections import Counter

    domain = urlparse(site.url).netloc.replace('www.', '')

    all_text       = ' '.join(p.content for p in pages if p.content)
    all_text_lower = all_text.lower()
    all_titles     = [p.title for p in pages if p.title]
    all_headings   = []
    for p in pages:
        if p.headings:
            all_headings.extend(h['text'] for h in p.headings)

    # Email
    emails = re.findall(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        all_text
    )
    email = emails[0] if emails else None

    # Phone
    phones = re.findall(r'(\+?[\d\s\-\(\)]{10,16})', all_text)
    phone  = phones[0].strip() if phones else None

    # Social links
    social_patterns = [
        r'https?://(?:www\.)?facebook\.com/[\w.]+',
        r'https?://(?:www\.)?twitter\.com/[\w.]+',
        r'https?://(?:www\.)?linkedin\.com/[\w/]+',
        r'https?://(?:www\.)?instagram\.com/[\w.]+',
        r'https?://(?:www\.)?youtube\.com/[\w/]+',
        r'https?://(?:www\.)?github\.com/[\w.]+',
    ]
    social_links = []
    for pattern in social_patterns:
        found = re.findall(pattern, all_text)
        social_links.extend(found[:1])

    # Topics from headings
    heading_words = []
    for h in all_headings[:30]:
        words = [
            w.lower() for w in h.split()
            if len(w) > 4 and w.isalpha()
        ]
        heading_words.extend(words)

    stop_words = {
        'about','contact','privacy','terms','policy',
        'cookie','login','register','search','category',
        'archive','page','posts','comments','reply',
        'click','here','read','more','view','home',
    }
    topic_counts = Counter(
        w for w in heading_words if w not in stop_words
    )
    main_topics = [w for w, _ in topic_counts.most_common(6)]

    # Business type
    type_keywords = {
        'e-commerce':    ['cart','checkout','buy','shop','price','product','order'],
        'blog':          ['post','article','author','published','comment','read'],
        'portfolio':     ['portfolio','project','work','design','creative','client'],
        'news':          ['news','breaking','headline','reporter','journalist','latest'],
        'education':     ['course','learn','student','tutorial','lesson','training'],
        'corporate':     ['services','solutions','enterprise','clients','team','company'],
        'documentation': ['docs','documentation','api','reference','guide','function'],
    }
    scores = {
        btype: sum(all_text_lower.count(kw) for kw in kws)
        for btype, kws in type_keywords.items()
    }
    business_type = max(scores, key=scores.get) if scores else 'website'

    # Description
    meta_descs = [
        p.meta_description for p in pages
        if p.meta_description and len(p.meta_description) > 20
    ]
    description = meta_descs[0] if meta_descs else (
        f"Website at {domain} — {len(pages)} pages scraped."
    )

    # Key facts
    total_words = sum(p.word_count for p in pages)
    key_facts = [
        f"{len(pages)} pages discovered and scraped",
        f"{total_words:,} total words extracted",
        f"Primary scrape mode: {site.scrape_mode or 'http'}",
    ]
    if email:
        key_facts.append(f"Contact email: {email}")
    if main_topics:
        key_facts.append(f"Main topics: {', '.join(main_topics[:3])}")
    if social_links:
        key_facts.append(f"{len(social_links)} social profile(s) found")

    # Language
    sample = all_text[:300].lower()
    language = 'English' if any(
        w in sample for w in ['the','and','for','this','with','that']
    ) else 'Unknown'

    # Products from headings
    products = list(set(
        h for h in all_headings[:20]
        if 5 < len(h) < 80
    ))[:5]

    return {
        'business_name':       all_titles[0] if all_titles else domain,
        'business_type':       business_type,
        'description':         description[:400],
        'main_topics':         main_topics[:6],
        'products_services':   products,
        'contact_email':       email,
        'contact_phone':       phone,
        'location':            None,
        'social_links':        list(set(social_links))[:5],
        'technologies':        [site.scrape_mode or 'http'],
        'key_facts':           key_facts,
        'sentiment':           'neutral',
        'language':            language,
        'total_pages_analyzed':len(pages),
        'extraction_method':   'rule-based',
    }
