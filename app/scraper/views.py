import os
import re
import logging
import urllib.parse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import render
from django.http import FileResponse, HttpResponse
from django.views import View
from .models import ScrapedSite, ScrapedPage, AnalysisResult

logger = logging.getLogger(__name__)


class DashboardView(View):
    def get(self, request):
        return render(request, "scraper/dashboard.html")


class ScrapeView(APIView):
    def post(self, request):
        from .tasks import scrape_site
        url   = request.data.get("url")
        depth = int(request.data.get("depth", 5))
        depth = max(1, min(10, depth))
        if not url:
            return Response(
                {"error": "url is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        site, created = ScrapedSite.objects.get_or_create(url=url)
        if created or site.status in ("failed", "pending"):
            site.status       = "pending"
            site.scrape_depth = depth
            site.save()
            scrape_site.delay(site.id)
        return Response({
            "id":      site.id,
            "url":     site.url,
            "status":  site.status,
            "depth":   site.scrape_depth,
            "created": created,
        })

    def get(self, request):
        sites = ScrapedSite.objects.all().order_by("-created_at")
        data  = []
        for site in sites:
            pages        = ScrapedPage.objects.filter(site=site)
            has_analysis = AnalysisResult.objects.filter(site=site).exists()
            data.append({
                "id":                 site.id,
                "url":                site.url,
                "status":             site.status,
                "scrape_mode":        site.scrape_mode,
                "scrape_depth":       site.scrape_depth,
                "pages_found":        pages.count(),
                "pages_with_content": pages.exclude(content="").count(),
                "total_words":        sum(p.word_count for p in pages),
                "has_pdf":            bool(site.pdf_file),
                "has_analysis":       has_analysis,
                "created_at":         site.created_at.isoformat(),
            })
        return Response(data)


class StatusView(APIView):
    def get(self, request, pk):
        try:
            site         = ScrapedSite.objects.get(pk=pk)
            pages        = ScrapedPage.objects.filter(site=site)
            has_analysis = AnalysisResult.objects.filter(site=site).exists()
            return Response({
                "id":                 site.id,
                "url":                site.url,
                "status":             site.status,
                "scrape_mode":        site.scrape_mode,
                "scrape_depth":       site.scrape_depth,
                "pages_found":        pages.count(),
                "pages_with_content": pages.exclude(content="").count(),
                "total_words":        sum(p.word_count for p in pages),
                "has_pdf":            bool(site.pdf_file),
                "has_analysis":       has_analysis,
                "created_at":         site.created_at.isoformat(),
                "scrape_started":     site.scrape_started.isoformat() if site.scrape_started else None,
                "scrape_finished":    site.scrape_finished.isoformat() if site.scrape_finished else None,
                "scrape_duration":    site.scrape_duration,
                "pages_per_second":   site.pages_per_second,
                "sample_pages": [
                    {
                        "url":        p.page_url,
                        "title":      p.title,
                        "word_count": p.word_count,
                    }
                    for p in pages.exclude(content="")[:10]
                ],
            })
        except ScrapedSite.DoesNotExist:
            return Response(
                {"error": "Not found"},
                status=status.HTTP_404_NOT_FOUND
            )

    def delete(self, request, pk):
        try:
            ScrapedSite.objects.get(pk=pk).delete()
            return Response({"message": "Deleted"})
        except ScrapedSite.DoesNotExist:
            return Response(
                {"error": "Not found"},
                status=status.HTTP_404_NOT_FOUND
            )


class AnalysisView(APIView):
    def get(self, request, pk):
        try:
            site     = ScrapedSite.objects.get(pk=pk)
            analysis = AnalysisResult.objects.get(site=site)
            return Response({
                "site_id":        site.id,
                "url":            site.url,
                "extracted_data": analysis.extracted_data,
                "created_at":     analysis.created_at.isoformat(),
            })
        except ScrapedSite.DoesNotExist:
            return Response(
                {"error": "Site not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except AnalysisResult.DoesNotExist:
            return Response(
                {"error": "Analysis not ready yet"},
                status=status.HTTP_404_NOT_FOUND
            )

    def post(self, request, pk):
        from .tasks import run_agent
        try:
            site = ScrapedSite.objects.get(pk=pk)
            run_agent.delay(site.id)
            return Response({"message": "Analysis started"})
        except ScrapedSite.DoesNotExist:
            return Response(
                {"error": "Not found"},
                status=status.HTTP_404_NOT_FOUND
            )


class PDFView(APIView):
    def get(self, request, pk):
        try:
            site = ScrapedSite.objects.get(pk=pk)
            if not site.pdf_file:
                return Response(
                    {"error": "PDF not generated yet"},
                    status=status.HTTP_404_NOT_FOUND
                )
            pdf_path = "/app/media/" + str(site.pdf_file)
            if not os.path.exists(pdf_path):
                return Response(
                    {"error": "PDF file missing on disk"},
                    status=status.HTTP_404_NOT_FOUND
                )
            response = FileResponse(
                open(pdf_path, "rb"),
                content_type="application/pdf"
            )
            response["Content-Disposition"] = (
                "attachment; filename=scrape_" + str(pk) + ".pdf"
            )
            return response
        except ScrapedSite.DoesNotExist:
            return Response(
                {"error": "Not found"},
                status=status.HTTP_404_NOT_FOUND
            )

    def post(self, request, pk):
        from .tasks import generate_pdf
        try:
            site = ScrapedSite.objects.get(pk=pk)
            generate_pdf.delay(site.id)
            return Response({"message": "PDF generation started"})
        except ScrapedSite.DoesNotExist:
            return Response(
                {"error": "Not found"},
                status=status.HTTP_404_NOT_FOUND
            )


class SearchView(APIView):
    def get(self, request, pk):
        query = request.query_params.get("q", "").strip()
        if not query or len(query) < 2:
            return Response(
                {"error": "Query too short"},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            site    = ScrapedSite.objects.get(pk=pk)
            pages   = ScrapedPage.objects.filter(
                site=site
            ).exclude(content="")
            results = []
            ql      = query.lower()
            for page in pages:
                if ql not in page.content.lower():
                    continue
                idx         = page.content.lower().find(ql)
                start       = max(0, idx - 120)
                end         = min(len(page.content), idx + 200)
                snippet     = page.content[start:end].strip()
                highlighted = re.sub(
                    "(" + re.escape(query) + ")",
                    r"<mark>\1</mark>",
                    snippet,
                    flags=re.IGNORECASE
                )
                results.append({
                    "url":     page.page_url,
                    "title":   page.title or page.page_url,
                    "snippet": "..." + highlighted + "...",
                    "count":   page.content.lower().count(ql),
                    "words":   page.word_count,
                })
            results.sort(key=lambda x: x["count"], reverse=True)
            return Response({
                "query":   query,
                "site":    site.url,
                "total":   len(results),
                "results": results[:20],
            })
        except ScrapedSite.DoesNotExist:
            return Response(
                {"error": "Site not found"},
                status=status.HTTP_404_NOT_FOUND
            )


class ExportView(APIView):
    def get(self, request, pk):
        fmt = request.query_params.get("format", "json").lower()
        try:
            site     = ScrapedSite.objects.get(pk=pk)
            pages    = list(ScrapedPage.objects.filter(
                site=site
            ).order_by("-word_count"))
            analysis = None
            try:
                analysis = AnalysisResult.objects.get(site=site)
            except AnalysisResult.DoesNotExist:
                pass

            from .exporters import (
                export_json, export_csv_pages,
                export_csv_analysis, export_excel
            )

            domain = site.url.replace(
                "https://", ""
            ).replace("http://", "").split("/")[0]
            safe_d = urllib.parse.quote(domain, safe="")
            ts     = site.created_at.strftime("%Y%m%d")

            if fmt == "json":
                data = export_json(site, pages, analysis)
                resp = HttpResponse(
                    data, content_type="application/json"
                )
                resp["Content-Disposition"] = (
                    "attachment; filename=scrape_"
                    + safe_d + "_" + ts + ".json"
                )
                return resp

            elif fmt == "csv":
                data = export_csv_pages(pages)
                resp = HttpResponse(data, content_type="text/csv")
                resp["Content-Disposition"] = (
                    "attachment; filename=pages_"
                    + safe_d + "_" + ts + ".csv"
                )
                return resp

            elif fmt == "csv_analysis":
                if not analysis:
                    return Response(
                        {"error": "No analysis available"},
                        status=status.HTTP_404_NOT_FOUND
                    )
                data = export_csv_analysis(site, analysis)
                resp = HttpResponse(data, content_type="text/csv")
                resp["Content-Disposition"] = (
                    "attachment; filename=analysis_"
                    + safe_d + "_" + ts + ".csv"
                )
                return resp

            elif fmt == "excel":
                data = export_excel(site, pages, analysis)
                resp = HttpResponse(
                    data,
                    content_type=(
                        "application/vnd.openxmlformats-"
                        "officedocument.spreadsheetml.sheet"
                    )
                )
                resp["Content-Disposition"] = (
                    "attachment; filename=scrape_"
                    + safe_d + "_" + ts + ".xlsx"
                )
                return resp

            else:
                return Response(
                    {"error": "Unknown format: " + fmt},
                    status=status.HTTP_400_BAD_REQUEST
                )

        except ScrapedSite.DoesNotExist:
            return Response(
                {"error": "Site not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error("Export error: " + str(e))
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ScheduleView(APIView):
    def get(self, request):
        from .models import ScheduledScrape, ContentChange
        schedules = ScheduledScrape.objects.select_related("site").all()
        data = []
        for s in schedules:
            changes = ContentChange.objects.filter(
                site=s.site
            ).order_by("-detected_at")[:5]
            data.append({
                "id":        s.id,
                "site_id":   s.site.id,
                "url":       s.site.url,
                "frequency": s.frequency,
                "status":    s.status,
                "last_run":  s.last_run.isoformat() if s.last_run else None,
                "next_run":  s.next_run.isoformat() if s.next_run else None,
                "run_count": s.run_count,
                "recent_changes": [
                    {
                        "type":        c.change_type,
                        "description": c.description,
                        "detected_at": c.detected_at.isoformat(),
                    }
                    for c in changes
                ],
            })
        return Response(data)

    def post(self, request):
        from .models import ScheduledScrape
        from .tasks import _calc_next_run
        from django.utils import timezone
        site_id   = request.data.get("site_id")
        frequency = request.data.get("frequency", "daily")
        if not site_id:
            return Response(
                {"error": "site_id required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            site = ScrapedSite.objects.get(id=site_id)
        except ScrapedSite.DoesNotExist:
            return Response(
                {"error": "Site not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        schedule, created = ScheduledScrape.objects.update_or_create(
            site=site,
            defaults={
                "frequency": frequency,
                "status":    "active",
                "next_run":  _calc_next_run(frequency, timezone.now()),
            }
        )
        return Response({
            "id":        schedule.id,
            "site_id":   site.id,
            "url":       site.url,
            "frequency": schedule.frequency,
            "status":    schedule.status,
            "next_run":  schedule.next_run.isoformat(),
            "created":   created,
        })


class ScheduleDetailView(APIView):
    def patch(self, request, pk):
        from .models import ScheduledScrape
        from .tasks import _calc_next_run, scrape_and_detect
        from django.utils import timezone
        try:
            schedule  = ScheduledScrape.objects.get(pk=pk)
            frequency = request.data.get("frequency", schedule.frequency)
            action    = request.data.get("action", "")
            if action == "pause":
                schedule.status = "paused"
            elif action == "resume":
                schedule.status   = "active"
                schedule.next_run = _calc_next_run(
                    frequency, timezone.now()
                )
            elif action == "run_now":
                site      = schedule.site
                old_pages = list(
                    site.pages.exclude(content="").order_by("page_url")
                )
                site.status = "pending"
                site.save(update_fields=["status"])
                site.pages.all().delete()
                scrape_and_detect.delay(
                    site.id,
                    old_page_data=[
                        {
                            "url":        p.page_url,
                            "word_count": p.word_count,
                            "content":    p.content[:200],
                        }
                        for p in old_pages
                    ]
                )
                schedule.last_run  = timezone.now()
                schedule.run_count += 1
                schedule.next_run  = _calc_next_run(
                    frequency, timezone.now()
                )
            schedule.frequency = frequency
            schedule.save()
            return Response({
                "id":        schedule.id,
                "frequency": schedule.frequency,
                "status":    schedule.status,
                "next_run":  schedule.next_run.isoformat()
                             if schedule.next_run else None,
                "run_count": schedule.run_count,
            })
        except ScheduledScrape.DoesNotExist:
            return Response(
                {"error": "Schedule not found"},
                status=status.HTTP_404_NOT_FOUND
            )

    def delete(self, request, pk):
        from .models import ScheduledScrape
        try:
            ScheduledScrape.objects.get(pk=pk).delete()
            return Response({"message": "Schedule deleted"})
        except ScheduledScrape.DoesNotExist:
            return Response(
                {"error": "Not found"},
                status=status.HTTP_404_NOT_FOUND
            )


class ChangesView(APIView):
    def get(self, request, pk):
        from .models import ContentChange
        try:
            site    = ScrapedSite.objects.get(pk=pk)
            changes = ContentChange.objects.filter(
                site=site
            ).order_by("-detected_at")[:50]
            return Response({
                "site_id": site.id,
                "url":     site.url,
                "changes": [
                    {
                        "id":          c.id,
                        "type":        c.change_type,
                        "description": c.description,
                        "old_value":   c.old_value,
                        "new_value":   c.new_value,
                        "detected_at": c.detected_at.isoformat(),
                    }
                    for c in changes
                ],
            })
        except ScrapedSite.DoesNotExist:
            return Response(
                {"error": "Site not found"},
                status=status.HTTP_404_NOT_FOUND
            )


class PageListView(APIView):
    def get(self, request, pk):
        try:
            site      = ScrapedSite.objects.get(pk=pk)
            pages     = ScrapedPage.objects.filter(
                site=site
            ).order_by("-word_count")
            min_words = int(request.query_params.get("min_words", 0))
            q         = request.query_params.get("q", "").strip().lower()
            if min_words:
                pages = pages.filter(word_count__gte=min_words)
            page_list = list(pages)
            if q:
                page_list = [
                    p for p in page_list
                    if q in p.title.lower() or q in p.page_url.lower()
                ]
            return Response({
                "site_id": site.id,
                "url":     site.url,
                "depth":   site.scrape_depth,
                "total":   len(page_list),
                "pages": [
                    {
                        "id":               p.id,
                        "url":              p.page_url,
                        "title":            p.title or "Untitled",
                        "word_count":       p.word_count,
                        "meta_description": p.meta_description,
                        "headings":         p.headings[:5] if p.headings else [],
                        "has_content":      bool(p.content),
                    }
                    for p in page_list
                ],
            })
        except ScrapedSite.DoesNotExist:
            return Response(
                {"error": "Site not found"},
                status=status.HTTP_404_NOT_FOUND
            )


class PageDetailView(APIView):
    def get(self, request, pk):
        try:
            page = ScrapedPage.objects.select_related("site").get(pk=pk)
            return Response({
                "id":               page.id,
                "site_id":          page.site.id,
                "url":              page.page_url,
                "title":            page.title or "Untitled",
                "word_count":       page.word_count,
                "meta_description": page.meta_description,
                "headings":         page.headings,
                "content":          page.content,
            })
        except ScrapedPage.DoesNotExist:
            return Response(
                {"error": "Page not found"},
                status=status.HTTP_404_NOT_FOUND
            )


class MultiPageAnalysisView(APIView):
    def post(self, request):
        page_ids = request.data.get("page_ids", [])
        query    = request.data.get("query", "").strip()

        if not page_ids:
            return Response(
                {"error": "page_ids required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if len(page_ids) > 50:
            return Response(
                {"error": "Maximum 50 pages per analysis"},
                status=status.HTTP_400_BAD_REQUEST
            )

        pages = ScrapedPage.objects.filter(
            id__in=page_ids
        ).select_related("site")

        if not pages.exists():
            return Response(
                {"error": "No pages found"},
                status=status.HTTP_404_NOT_FOUND
            )

        site        = pages.first().site
        total_words = 0

        for page in pages.order_by("-word_count"):
            total_words += page.word_count

        from .agent import extract_key_values

        class PageProxy:
            def __init__(self, p):
                self.page_url         = p.page_url
                self.title            = p.title
                self.content          = p.content
                self.word_count       = p.word_count
                self.meta_description = p.meta_description
                self.headings         = p.headings

        page_proxies = [PageProxy(p) for p in pages]
        result       = extract_key_values(site, page_proxies)

        keyword_hits = []
        if query:
            ql = query.lower()
            for page in pages:
                if not page.content or ql not in page.content.lower():
                    continue
                matches = list(re.finditer(
                    re.escape(query), page.content, re.IGNORECASE
                ))
                for m in matches[:3]:
                    start   = max(0, m.start() - 150)
                    end     = min(len(page.content), m.end() + 150)
                    snippet = page.content[start:end].strip()
                    highlighted = re.sub(
                        "(" + re.escape(query) + ")",
                        "**" + r"\1" + "**",
                        snippet,
                        flags=re.IGNORECASE
                    )
                    keyword_hits.append({
                        "page_id":    page.id,
                        "page_title": page.title or page.page_url,
                        "page_url":   page.page_url,
                        "context":    "..." + highlighted + "...",
                    })

        return Response({
            "pages_analyzed": len(page_ids),
            "total_words":    total_words,
            "query":          query,
            "keyword_hits":   keyword_hits[:30],
            "extracted_data": result,
        })
