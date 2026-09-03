"""Public, unauthenticated unsubscribe endpoints.

Plain Django views (not Ninja) because these render HTML pages for humans and
mail clients rather than JSON. They are mounted under /api/ in prospect.urls so
nginx routes them to Django in production without any new location block.

GET  shows a confirmation page and changes nothing — mail scanners and
     link-preview bots fetch every URL in a message, so a mutating GET would
     unsubscribe people who never clicked.
POST performs the opt-out. It also serves the List-Unsubscribe-Post one-click
     flow, which arrives from the mail provider without a CSRF token.
"""

import logging

from django.core import signing
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import SentEmail, Unsubscribe
from .services.unsubscribe import load_token

logger = logging.getLogger(__name__)


def _client_ip(request):
    """Real client IP: nginx sets X-Forwarded-For (nginx/production.conf)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def _is_one_click(request) -> bool:
    """RFC 8058 one-click POST sent by the mail client, not by our own form."""
    return request.POST.get("List-Unsubscribe") == "One-Click"


@csrf_exempt
@require_http_methods(["GET", "POST"])
def unsubscribe(request, token: str):
    try:
        data = load_token(token)
    except signing.BadSignature:
        logger.warning("Invalid unsubscribe token received")
        # HTTP 200 and a generic page: never reveal whether a token is real.
        return render(request, "emails/unsubscribe_invalid.html")

    email = data["email"]
    sent_email_id = data["sent_email_id"]

    if request.method == "GET":
        already = Unsubscribe.objects.filter(email=email).exists()
        return render(
            request,
            "emails/unsubscribe_confirm.html",
            {"email": email, "token": token, "already_unsubscribed": already},
        )

    sent_email = None
    if sent_email_id:
        sent_email = SentEmail.objects.filter(id=sent_email_id).first()

    source = Unsubscribe.SOURCE_LIST_HEADER if _is_one_click(request) else Unsubscribe.SOURCE_LINK

    _, created = Unsubscribe.objects.get_or_create(
        email=email,
        defaults={
            "sent_email": sent_email,
            "company_name": sent_email.company_name if sent_email else "",
            "twenty_crm_id": sent_email.twenty_crm_id if sent_email else "",
            "ip_address": _client_ip(request),
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:500],
            "source": source,
        },
    )

    if created:
        logger.info(f"Unsubscribed {email} (source={source}, sent_email={sent_email_id})")

    return render(request, "emails/unsubscribe_done.html", {"email": email})
