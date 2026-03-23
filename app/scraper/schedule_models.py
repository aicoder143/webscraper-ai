from django.db import models
from .models import ScrapedSite


class ScheduledScrape(models.Model):
    FREQUENCY_CHOICES = [
        ("hourly",  "Every Hour"),
        ("daily",   "Every Day"),
        ("weekly",  "Every Week"),
        ("monthly", "Every Month"),
    ]
    STATUS_CHOICES = [
        ("active",   "Active"),
        ("paused",   "Paused"),
        ("error",    "Error"),
    ]
    site        = models.OneToOneField(
        ScrapedSite, on_delete=models.CASCADE,
        related_name="schedule"
    )
    frequency   = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default="daily"
    )
    status      = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active"
    )
    last_run    = models.DateTimeField(null=True, blank=True)
    next_run    = models.DateTimeField(null=True, blank=True)
    run_count   = models.IntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.site.url} — {self.frequency}"


class ContentChange(models.Model):
    CHANGE_CHOICES = [
        ("new_pages",     "New Pages Found"),
        ("removed_pages", "Pages Removed"),
        ("content_change","Content Changed"),
        ("word_count",    "Word Count Changed"),
    ]
    site        = models.ForeignKey(
        ScrapedSite, on_delete=models.CASCADE,
        related_name="changes"
    )
    change_type = models.CharField(
        max_length=30,
        choices=CHANGE_CHOICES
    )
    description = models.TextField()
    old_value   = models.TextField(blank=True)
    new_value   = models.TextField(blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-detected_at"]

    def __str__(self):
        return f"{self.site.url} — {self.change_type}"
