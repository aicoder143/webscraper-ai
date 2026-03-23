from django.contrib import admin
from .models import ScrapedSite, ScrapedPage, AnalysisResult


@admin.register(ScrapedSite)
class ScrapedSiteAdmin(admin.ModelAdmin):
    list_display  = ('url', 'status', 'scrape_mode', 'created_at')
    list_filter   = ('status', 'scrape_mode')
    search_fields = ('url',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ScrapedPage)
class ScrapedPageAdmin(admin.ModelAdmin):
    list_display  = ('page_url', 'site', 'scraped_at')
    search_fields = ('page_url',)
    list_filter   = ('site',)


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display  = ('site', 'created_at')
    readonly_fields = ('created_at',)

from .models import ScheduledScrape, ContentChange


@admin.register(ScheduledScrape)
class ScheduledScrapeAdmin(admin.ModelAdmin):
    list_display  = ("site", "frequency", "status",
                     "last_run", "next_run", "run_count")
    list_filter   = ("frequency", "status")
    readonly_fields = ("last_run", "next_run", "run_count", "created_at")


@admin.register(ContentChange)
class ContentChangeAdmin(admin.ModelAdmin):
    list_display  = ("site", "change_type", "description", "detected_at")
    list_filter   = ("change_type",)
    readonly_fields = ("detected_at",)
