"""Mailgun delivery webhooks.

A plain Django view (not Ninja) because Mailgun, not a logged-in user, calls it:
authentication is the HMAC signature in the body, checked against the account's
webhook signing key. Mounted under /api/ in prospect.urls so nginx already
routes it to Django.

The Mailgun domain is shared with other apps, so most events that arrive may be
about mail that is not ours. Those are acknowledged with 200 and ignored —
anything else would make Mailgun retry them for hours.
"""

import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .services.delivery import apply_event, parse_event, verify_signature

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def mailgun_webhook(request):
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return HttpResponse(status=400)

    if not verify_signature(payload):
        logger.warning("Rejected Mailgun webhook with a bad signature")
        return HttpResponse(status=401)

    event = parse_event(payload.get("event-data"))
    if event is None:
        return JsonResponse({"ok": True, "result": "ignored"})

    result = apply_event(event)
    logger.info(f"Mailgun {event.kind} for {event.recipient}: {result}")
    return JsonResponse({"ok": True, "result": result})
