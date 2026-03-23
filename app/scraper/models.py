from django.db import models


class ScrapedSite(models.Model):
    STATUS_CHOICES = [
        ('pending',  'Pending'),
        ('scraping', 'Scraping'),
        ('done',     'Done'),
        ('failed',   'Failed'),
    ]
    url         = models.URLField(unique=True)
    status      = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )
    scrape_mode  = models.CharField(max_length=20, blank=True)
    scrape_depth = models.IntegerField(default=5)
    pdf_file     = models.FileField(upload_to='pdfs/', blank=True, null=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.url


class ScrapedPage(models.Model):
    site             = models.ForeignKey(
        ScrapedSite, on_delete=models.CASCADE, related_name='pages'
    )
    page_url         = models.URLField()
    title            = models.CharField(max_length=500, blank=True)
    content          = models.TextField(blank=True)
    meta_description = models.TextField(blank=True)
    headings         = models.JSONField(default=list)
    word_count       = models.IntegerField(default=0)
    scraped_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('site', 'page_url')

    def __str__(self):
        return self.page_url


class AnalysisResult(models.Model):
    site           = models.OneToOneField(
        ScrapedSite, on_delete=models.CASCADE, related_name='analysis'
    )
    extracted_data = models.JSONField(default=dict)
    created_at     = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Analysis for {self.site.url}'


class ScheduledScrape(models.Model):
    FREQUENCY_CHOICES = [
        ("hourly",  "Every Hour"),
        ("daily",   "Every Day"),
        ("weekly",  "Every Week"),
        ("monthly", "Every Month"),
    ]
    STATUS_CHOICES = [
        ("active",  "Active"),
        ("paused",  "Paused"),
        ("error",   "Error"),
    ]
    site       = models.OneToOneField(
        ScrapedSite, on_delete=models.CASCADE,
        related_name="schedule"
    )
    frequency  = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default="daily"
    )
    status     = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active"
    )
    last_run   = models.DateTimeField(null=True, blank=True)
    next_run   = models.DateTimeField(null=True, blank=True)
    run_count  = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.site.url} — {self.frequency}"


class ContentChange(models.Model):
    CHANGE_CHOICES = [
        ("new_pages",      "New Pages Found"),
        ("removed_pages",  "Pages Removed"),
        ("content_change", "Content Changed"),
        ("word_count",     "Word Count Changed"),
    ]
    site        = models.ForeignKey(
        ScrapedSite, on_delete=models.CASCADE,
        related_name="changes"
    )
    change_type = models.CharField(
        max_length=30, choices=CHANGE_CHOICES
    )
    description = models.TextField()
    old_value   = models.TextField(blank=True)
    new_value   = models.TextField(blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-detected_at"]

    def __str__(self):
        return f"{self.site.url} — {self.change_type}"
