import os
import logging
from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, PageBreak, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

logger = logging.getLogger(__name__)

# ── Color palette ────────────────────────────────────────────────
DARK       = colors.HexColor('#0d1117')
ACCENT     = colors.HexColor('#00d4ff')
ACCENT2    = colors.HexColor('#00ff88')
LIGHT_GRAY = colors.HexColor('#f0f4f8')
MID_GRAY   = colors.HexColor('#8899aa')
BORDER     = colors.HexColor('#d0dce8')
WHITE      = colors.white


def build_styles():
    base = getSampleStyleSheet()

    styles = {
        'cover_title': ParagraphStyle(
            'cover_title',
            fontName='Helvetica-Bold',
            fontSize=28,
            textColor=DARK,
            spaceAfter=8,
            leading=34,
        ),
        'cover_url': ParagraphStyle(
            'cover_url',
            fontName='Helvetica',
            fontSize=13,
            textColor=ACCENT,
            spaceAfter=6,
        ),
        'cover_meta': ParagraphStyle(
            'cover_meta',
            fontName='Helvetica',
            fontSize=10,
            textColor=MID_GRAY,
            spaceAfter=4,
        ),
        'section_heading': ParagraphStyle(
            'section_heading',
            fontName='Helvetica-Bold',
            fontSize=16,
            textColor=DARK,
            spaceBefore=14,
            spaceAfter=6,
            borderPadding=(0, 0, 4, 0),
        ),
        'page_title': ParagraphStyle(
            'page_title',
            fontName='Helvetica-Bold',
            fontSize=13,
            textColor=DARK,
            spaceBefore=10,
            spaceAfter=4,
        ),
        'page_url': ParagraphStyle(
            'page_url',
            fontName='Helvetica-Oblique',
            fontSize=8,
            textColor=ACCENT,
            spaceAfter=6,
        ),
        'body_text': ParagraphStyle(
            'body_text',
            fontName='Helvetica',
            fontSize=9,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=6,
            leading=14,
            alignment=TA_JUSTIFY,
        ),
        'meta_label': ParagraphStyle(
            'meta_label',
            fontName='Helvetica-Bold',
            fontSize=8,
            textColor=MID_GRAY,
            spaceAfter=2,
        ),
        'meta_value': ParagraphStyle(
            'meta_value',
            fontName='Helvetica',
            fontSize=9,
            textColor=DARK,
            spaceAfter=4,
        ),
        'toc_item': ParagraphStyle(
            'toc_item',
            fontName='Helvetica',
            fontSize=9,
            textColor=DARK,
            spaceAfter=3,
            leftIndent=10,
        ),
        'stat_number': ParagraphStyle(
            'stat_number',
            fontName='Helvetica-Bold',
            fontSize=22,
            textColor=ACCENT,
            alignment=TA_CENTER,
            spaceAfter=2,
        ),
        'stat_label': ParagraphStyle(
            'stat_label',
            fontName='Helvetica',
            fontSize=8,
            textColor=MID_GRAY,
            alignment=TA_CENTER,
        ),
        'heading_item': ParagraphStyle(
            'heading_item',
            fontName='Helvetica',
            fontSize=9,
            textColor=colors.HexColor('#445566'),
            spaceAfter=2,
            leftIndent=8,
        ),
    }
    return styles


def truncate(text: str, max_chars: int = 800) -> str:
    text = str(text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(' ', 1)[0] + '...'


def safe_paragraph(text: str, style) -> Paragraph:
    import re
    text = str(text).strip()
    # Escape XML special chars
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    # Remove non-printable chars
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    try:
        return Paragraph(text, style)
    except Exception:
        return Paragraph('(content unavailable)', style)


def generate_pdf(site, pages, output_path: str) -> str:
    """
    Generate a structured PDF from scraped site data.
    Returns the output file path.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=20*mm,
        rightMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm,
        title=f"Scrape Report — {site.url}",
        author="WebScraper AI",
    )

    styles   = build_styles()
    elements = []
    W = A4[0] - 40*mm  # usable width

    # ── Cover page ───────────────────────────────────────────────
    elements.append(Spacer(1, 20*mm))

    # Accent bar
    elements.append(Table(
        [['']],
        colWidths=[W],
        rowHeights=[4],
        style=TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), ACCENT),
            ('LINEBELOW', (0,0), (-1,-1), 0, WHITE),
        ])
    ))
    elements.append(Spacer(1, 8*mm))

    # Site domain as title
    from urllib.parse import urlparse
    domain = urlparse(site.url).netloc or site.url
    elements.append(safe_paragraph(domain, styles['cover_title']))
    elements.append(safe_paragraph(site.url, styles['cover_url']))
    elements.append(Spacer(1, 4*mm))

    # Report metadata
    total_words = sum(p.word_count for p in pages)
    pages_with_content = [p for p in pages if p.word_count > 0]

    elements.append(safe_paragraph(
        f"Generated: {datetime.now().strftime('%B %d, %Y at %H:%M')}",
        styles['cover_meta']
    ))
    elements.append(safe_paragraph(
        f"Scrape mode: {site.scrape_mode or 'http'}  |  "
        f"Pages discovered: {len(pages)}  |  "
        f"Pages with content: {len(pages_with_content)}",
        styles['cover_meta']
    ))
    elements.append(Spacer(1, 8*mm))

    # Stats table
    stats_data = [[
        Paragraph(str(len(pages)),            styles['stat_number']),
        Paragraph(str(len(pages_with_content)), styles['stat_number']),
        Paragraph(f"{total_words:,}",         styles['stat_number']),
        Paragraph(site.scrape_mode or 'http', styles['stat_number']),
    ],[
        Paragraph('Pages Found',    styles['stat_label']),
        Paragraph('With Content',   styles['stat_label']),
        Paragraph('Total Words',    styles['stat_label']),
        Paragraph('Scrape Mode',    styles['stat_label']),
    ]]

    col_w = W / 4
    stats_table = Table(
        stats_data,
        colWidths=[col_w]*4,
        rowHeights=[30, 16],
    )
    stats_table.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,-1), LIGHT_GRAY),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [LIGHT_GRAY, WHITE]),
        ('BOX',         (0,0), (-1,-1), 0.5, BORDER),
        ('INNERGRID',   (0,0), (-1,-1), 0.5, BORDER),
        ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',  (0,0), (-1,-1), 6),
        ('BOTTOMPADDING',(0,0),(-1,-1), 6),
        ('ROUNDEDCORNERS', [4]),
    ]))
    elements.append(stats_table)
    elements.append(Spacer(1, 8*mm))

    # Accent bar
    elements.append(Table(
        [['']],
        colWidths=[W],
        rowHeights=[2],
        style=TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), BORDER),
        ])
    ))

    elements.append(PageBreak())

    # ── Table of Contents ────────────────────────────────────────
    elements.append(safe_paragraph('Table of Contents', styles['section_heading']))
    elements.append(HRFlowable(width=W, thickness=0.5, color=BORDER))
    elements.append(Spacer(1, 4*mm))

    for i, page in enumerate(pages_with_content[:50], 1):
        title = page.title or page.page_url
        elements.append(safe_paragraph(
            f"{i}.  {truncate(title, 80)}",
            styles['toc_item']
        ))

    elements.append(PageBreak())

    # ── Page content sections ────────────────────────────────────
    elements.append(safe_paragraph('Scraped Content', styles['section_heading']))
    elements.append(HRFlowable(width=W, thickness=0.5, color=BORDER))

    for i, page in enumerate(pages_with_content[:50], 1):
        elements.append(Spacer(1, 4*mm))

        # Page header row
        header_data = [[
            safe_paragraph(
                truncate(page.title or 'Untitled', 80),
                styles['page_title']
            ),
            safe_paragraph(
                f"#{i}  |  {page.word_count:,} words",
                styles['meta_label']
            ),
        ]]
        header_table = Table(
            header_data,
            colWidths=[W*0.75, W*0.25],
        )
        header_table.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,-1), LIGHT_GRAY),
            ('TOPPADDING',    (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING',   (0,0), (-1,-1), 8),
            ('RIGHTPADDING',  (0,0), (-1,-1), 8),
            ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN',         (1,0), (1,0),   'RIGHT'),
        ]))
        elements.append(header_table)

        # URL
        elements.append(safe_paragraph(
            truncate(page.page_url, 100),
            styles['page_url']
        ))

        # Meta description if available
        if page.meta_description:
            elements.append(safe_paragraph(
                f"Summary: {truncate(page.meta_description, 200)}",
                styles['meta_label']
            ))
            elements.append(Spacer(1, 2*mm))

        # Headings
        if page.headings:
            for h in page.headings[:5]:
                prefix = '▸' if h['level'] == 'h1' else '  ›'
                elements.append(safe_paragraph(
                    f"{prefix} {truncate(h['text'], 100)}",
                    styles['heading_item']
                ))
            elements.append(Spacer(1, 2*mm))

        # Body content — first 600 words
        if page.content:
            words = page.content.split()
            preview = ' '.join(words[:600])
            if len(words) > 600:
                preview += f'... [{len(words)-600} more words]'
            elements.append(safe_paragraph(preview, styles['body_text']))

        # Separator
        elements.append(HRFlowable(
            width=W, thickness=0.3,
            color=BORDER, spaceAfter=2
        ))

    logger.info(
        f"PDF built — {len(pages_with_content)} pages, "
        f"{total_words:,} words → {output_path}"
    )

    doc.build(elements)
    return output_path
