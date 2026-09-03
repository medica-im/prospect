"""Liveness/readiness endpoint used by the container healthcheck.

Plain Django rather than a Ninja route: this has to answer even when the API
layer is the thing that is broken, and it must not require auth, a schema or
a database migration to exist.
"""

from django.db import connection
from django.http import JsonResponse


def health(request):
    """Report whether this container can actually serve traffic.

    Checks the database, because "gunicorn is listening" is not the same as
    "the app works": a container that cannot reach postgres accepts the
    connection and then fails every real request. A deploy that only waited
    for the port would call that a success.

    Deliberately does not touch redis or rabbitmq. Celery needs them, but the
    web container can serve pages without them, and folding them in here would
    make an unrelated outage look like a failed release.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 - any failure means not ready
        return JsonResponse(
            {"status": "error", "database": str(exc)},
            status=503,
        )

    return JsonResponse({"status": "ok", "database": "ok"})
