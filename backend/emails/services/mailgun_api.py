"""Read-side Mailgun API access (webhooks, events, suppression lists).

Separate from services/mailgun.py, which only sends. This needs the private API
key (MAILGUN_API_KEY): the sending key cannot read events or manage webhooks.
The region (EU/US) comes from MAILGUN_API_URL, the same URL used for sending.
"""

from urllib.parse import urlsplit

import httpx
from django.conf import settings

# Mailgun accepts a few URLs per webhook event type; the domain may be shared
# with another app (clinic-cms), so ours is added next to the existing ones.
MAX_WEBHOOK_URLS = 3


class MailgunApiError(Exception):
    pass


def api_base() -> str:
    """Scheme and host of the Mailgun API in our region, e.g. https://api.eu.mailgun.net."""
    parts = urlsplit(settings.MAILGUN_API_URL)
    if not (parts.scheme and parts.netloc):
        raise MailgunApiError("MAILGUN_API_URL is not set.")
    return f"{parts.scheme}://{parts.netloc}"


def client() -> httpx.Client:
    if not settings.MAILGUN_API_KEY:
        raise MailgunApiError("MAILGUN_API_KEY is not set.")
    if not settings.MAILGUN_DOMAIN:
        raise MailgunApiError("MAILGUN_DOMAIN is not set.")
    return httpx.Client(
        base_url=api_base(), auth=("api", settings.MAILGUN_API_KEY), timeout=30,
    )


def get_json(http: httpx.Client, url: str, params: dict | None = None) -> dict:
    response = http.get(url, params=params)
    if response.status_code >= 400:
        raise MailgunApiError(f"GET {url} -> {response.status_code}: {response.text[:300]}")
    return response.json()


def paginate(http: httpx.Client, url: str, params: dict | None = None):
    """Yield every item of a Mailgun list endpoint, following `paging.next`."""
    page = get_json(http, url, params)
    while page.get("items"):
        yield from page["items"]
        next_url = (page.get("paging") or {}).get("next")
        if not next_url:
            return
        page = get_json(http, next_url)
