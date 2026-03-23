from celery import shared_task
import logging
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def get_depth_config(depth: int) -> dict:
    """
    Maps slider value 1-10 to scraping parameters.
    1 = very light (homepage only)
    5 = balanced (50 pages, 1s delay)
    10 = deep (200 pages, no delay, full content)
    """
    configs = {
        1:  {"max_pages": 5,   "delay": 3.0, "content_limit": 200,  "label": "Surface"},
        2:  {"max_pages": 10,  "delay": 2.0, "content_limit": 300,  "label": "Light"},
        3:  {"max_pages": 20,  "delay": 1.5, "content_limit": 400,  "label": "Shallow"},
        4:  {"max_pages": 30,  "delay": 1.0, "content_limit": 500,  "label": "Moderate-light"},
        5:  {"max_pages": 50,  "delay": 1.0, "content_limit": 800,  "label": "Balanced"},
        6:  {"max_pages": 75,  "delay": 0.8, "content_limit": 1000, "label": "Moderate-deep"},
        7:  {"max_pages": 100, "delay": 0.5, "content_limit": 2000, "label": "Deep"},
        8:  {"max_pages": 150, "delay": 0.3, "content_limit": 3000, "label": "Very deep"},
        9:  {"max_pages": 175, "delay": 0.2, "content_limit": 5000, "label": "Thorough"},
        10: {"max_pages": 200, "delay": 0.0, "content_limit": 9999, "label": "Maximum"},
    }
    return configs.get(max(1, min(10, depth)), configs[5])



@shared_task(bind=True, max_retries=3)
def scrape_site(self, site_id: int):
    from .models import ScrapedSite, ScrapedPage
    from .sitemap import discover_urls
    from .detector import detect_rendering_mode
    from .spiders import scrape_page

    try:
        site = ScrapedSite.objects.get(id=site_id)
        site.status = "scraping"
        site.save(update_fields=["status"])

        # Get depth configuration
        depth  = getattr(site, "scrape_depth", 5)
        cfg    = get_depth_config(depth)
        logger.info(
            f"[{site_id}] Depth={depth} ({cfg['label']}) "
            f"max_pages={cfg['max_pages']} delay={cfg['delay']}s"
        )

        logger.info(f"[{site_id}] Discovering: {site.url}")
        discovery = discover_urls(site.url, max_pages=cfg["max_pages"])
        logger.info(f"[{site_id}] Found {discovery['total_found']} URLs")

        mode = detect_rendering_mode(site.url)
        site.scrape_mode = mode
        site.save(update_fields=["scrape_mode"])

        scraped_count = 0
        failed_count  = 0

        for item in discovery["urls"]:
            page_url = item["url"]
            page, created = ScrapedPage.objects.get_or_create(
                site=site, page_url=page_url,
                defaults={
                    "title": "", "content": "",
                    "meta_description": "",
                    "headings": [], "word_count": 0,
                }
            )
            if not created and page.word_count > 0:
                continue
            result = scrape_page(page_url, mode=mode)
            if result.get("success"):
                raw_content = result.get("content", "")
                # Apply content limit based on depth
                words       = raw_content.split()
                limited     = " ".join(words[:cfg["content_limit"]])
                word_count  = len([w for w in limited.split() if len(w) > 1])
                if word_count == 0:
                    word_count = result.get("word_count", 0)
                page.title            = result.get("title", "")[:500]
                page.content          = limited
                page.meta_description = result.get("meta_description", "")
                page.headings         = result.get("headings", [])
                page.word_count       = word_count
                page.save(update_fields=[
                    "title", "content", "meta_description",
                    "headings", "word_count"
                ])
                scraped_count += 1
                logger.info(
                    f"[{site_id}] OK [{scraped_count}] "
                    f"{page_url[:55]} — {word_count}w"
                )
            else:
                failed_count += 1
            if cfg["delay"] > 0:
                time.sleep(cfg["delay"])

        logger.info(
            f"[{site_id}] Done — "
            f"scraped:{scraped_count} failed:{failed_count}"
        )
        site.status = "done"
        site.save(update_fields=["status"])

        generate_pdf.apply_async(
            args=[site_id],
            link=run_agent.si(site_id)
        )
        return {
            "site_id": site_id,
            "scraped": scraped_count,
            "failed":  failed_count,
            "mode":    mode,
        }

    except ScrapedSite.DoesNotExist:
        return {"error": f"Site {site_id} not found"}
    except Exception as exc:
        logger.error(f"[{site_id}] Exception: {exc}")
        try:
            site.status = "failed"
            site.save(update_fields=["status"])
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True)
def generate_pdf(self, site_id: int):
    from .models import ScrapedSite, ScrapedPage
    from .pdf_generator import generate_pdf as build_pdf
    import os
    try:
        site  = ScrapedSite.objects.get(id=site_id)
        pages = ScrapedPage.objects.filter(
            site=site
        ).order_by("-word_count")
        if not pages.exists():
            return
        logger.info(f"[{site_id}] Generating PDF")
        output_path = f"/app/media/pdfs/site_{site_id}.pdf"
        os.makedirs("/app/media/pdfs", exist_ok=True)
        build_pdf(site, list(pages), output_path)
        site.pdf_file = f"pdfs/site_{site_id}.pdf"
        site.save(update_fields=["pdf_file"])
        logger.info(f"[{site_id}] PDF saved")
        return {"site_id": site_id}
    except Exception as exc:
        logger.error(f"[{site_id}] PDF error: {exc}")
        raise self.retry(exc=exc, countdown=30)


@shared_task(bind=True)
def run_agent(self, site_id: int):
    from .models import ScrapedSite, ScrapedPage, AnalysisResult
    from .agent import extract_key_values
    try:
        site  = ScrapedSite.objects.get(id=site_id)
        pages = ScrapedPage.objects.filter(
            site=site
        ).exclude(content="").order_by("-word_count")
        if not pages.exists():
            return
        logger.info(f"[{site_id}] Running AI analysis")
        result = extract_key_values(site, list(pages))
        AnalysisResult.objects.update_or_create(
            site=site,
            defaults={"extracted_data": result}
        )
        logger.info(f"[{site_id}] Analysis complete")
        return {"site_id": site_id}
    except Exception as exc:
        logger.error(f"[{site_id}] Agent error: {exc}")
        raise self.retry(exc=exc, countdown=30)


@shared_task
def run_scheduled_scrapes():
    """
    Phase 8 — Called by Celery Beat every 30 minutes.
    Checks all active schedules and triggers due scrapes.
    """
    from .models import ScheduledScrape
    from django.utils import timezone

    now      = timezone.now()
    due      = ScheduledScrape.objects.filter(
        status="active",
        next_run__lte=now
    )
    count    = due.count()
    logger.info(f"Scheduler: {count} scrapes due")

    for schedule in due:
        site = schedule.site
        logger.info(
            f"Scheduler: triggering {site.url} "
            f"(freq={schedule.frequency})"
        )

        # Snapshot old pages for change detection
        old_pages = list(
            site.pages.exclude(content="").order_by("page_url")
        )

        # Reset site for fresh scrape
        site.status = "pending"
        site.save(update_fields=["status"])

        # Delete old pages so fresh content is scraped
        site.pages.all().delete()

        # Trigger scrape — chain to change detection after
        scrape_and_detect.apply_async(
            args=[site.id],
            kwargs={"old_page_data": [
                {
                    "url":        p.page_url,
                    "word_count": p.word_count,
                    "content":    p.content[:200],
                }
                for p in old_pages
            ]}
        )

        # Update schedule timing
        schedule.last_run  = now
        schedule.run_count += 1
        schedule.next_run  = _calc_next_run(schedule.frequency, now)
        schedule.save()

    return {"triggered": count}


@shared_task(bind=True, max_retries=2)
def scrape_and_detect(self, site_id: int, old_page_data=None):
    """
    Re-scrape a site then run change detection.
    Used by the scheduler for periodic scrapes.
    """
    from .models import ScrapedSite, ScrapedPage, ContentChange
    from .change_detector import detect_changes, save_changes

    try:
        # Run the full scrape
        scrape_site(site_id)

        if not old_page_data:
            return {"site_id": site_id, "changes": 0}

        # Build simple page objects for comparison
        site      = ScrapedSite.objects.get(id=site_id)
        new_pages = list(
            ScrapedPage.objects.filter(site=site)
            .exclude(content="")
        )

        class SimplePage:
            def __init__(self, d):
                self.page_url   = d["url"]
                self.word_count = d["word_count"]
                self.content    = d.get("content", "")

        old_pages = [SimplePage(d) for d in old_page_data]

        # Detect changes
        changes = detect_changes(site, old_pages, new_pages)
        saved   = save_changes(site, changes)

        logger.info(
            f"[{site_id}] Change detection: "
            f"{len(changes)} changes found"
        )
        return {
            "site_id": site_id,
            "changes": len(changes),
        }

    except Exception as exc:
        logger.error(f"[{site_id}] Scrape+detect error: {exc}")
        raise self.retry(exc=exc, countdown=60)


def _calc_next_run(frequency: str, from_time) -> object:
    """Calculate the next run datetime based on frequency."""
    deltas = {
        "hourly":  timedelta(hours=1),
        "daily":   timedelta(days=1),
        "weekly":  timedelta(weeks=1),
        "monthly": timedelta(days=30),
    }
    return from_time + deltas.get(frequency, timedelta(days=1))
