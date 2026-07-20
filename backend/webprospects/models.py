from django.db import models


class HeadNounGender(models.Model):
    """Grammatical gender of an organisation-name head noun, for choosing the
    correct French definite article (la / le / l')."""

    GENDER_FEMININE = "f"
    GENDER_MASCULINE = "m"
    GENDER_UNKNOWN = "unknown"
    GENDER_CHOICES = [
        (GENDER_FEMININE, "Feminine (la)"),
        (GENDER_MASCULINE, "Masculine (le)"),
        (GENDER_UNKNOWN, "Unknown (needs review)"),
    ]

    # Lowercased, accent-preserving first term of a company name (e.g. "msp",
    # "pôle", "maison"). Acronyms are stored as-is ("cpts", "sisa").
    head_noun = models.CharField(max_length=100, unique=True)
    gender = models.CharField(
        max_length=10, choices=GENDER_CHOICES, default=GENDER_UNKNOWN)
    note = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Optional: expansion or reason (e.g. 'CPTS = communauté → f')")

    class Meta:
        ordering = ["head_noun"]

    def __str__(self):
        return f"{self.head_noun} ({self.gender})"


class WebProspectRun(models.Model):
    """Records one processing of a web page (e.g. an apmsl.fr listing)."""
    source_url = models.URLField(max_length=1000)
    scraper = models.CharField(
        max_length=50, default="apmsl",
        help_text="Scraper used, e.g. 'apmsl'")
    ask_confirmation = models.BooleanField(default=True)
    total = models.IntegerField(default=0)
    created_count = models.IntegerField(default=0)
    updated_count = models.IntegerField(default=0)
    skipped_count = models.IntegerField(default=0)
    already_present_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"WebProspectRun {self.id} - {self.source_url} ({self.created_at:%Y-%m-%d %H:%M})"


class WebProspectRecord(models.Model):
    """One MSP (or similar org) found on a page and its processing outcome."""

    STATUS_CREATED = "created"
    STATUS_UPDATED = "updated"
    STATUS_ALREADY_PRESENT = "already_present"
    STATUS_SKIPPED = "skipped"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_CREATED, "Created"),
        (STATUS_UPDATED, "Updated"),
        (STATUS_ALREADY_PRESENT, "Already present"),
        (STATUS_SKIPPED, "Skipped"),
        (STATUS_FAILED, "Failed"),
    ]

    run = models.ForeignKey(
        WebProspectRun, on_delete=models.CASCADE, related_name="records")
    name = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    twenty_company_id = models.CharField(max_length=255, blank=True, default="")
    missing_fields = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True, default="")
    # When a unique field (email) collided, the existing company that owns it.
    duplicate_company_id = models.CharField(max_length=255, blank=True, default="")
    duplicate_company_name = models.CharField(max_length=500, blank=True, default="")
    data = models.JSONField(
        default=dict, blank=True,
        help_text="Parsed source data for this record (for audit / re-parse)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} [{self.status}]"
