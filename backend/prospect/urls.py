from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import path
from ninja import NinjaAPI

from emails.api import router as emails_router
from emails.unsubscribe_views import unsubscribe
from prospect.auth_api import router as auth_router
from prospect.health import health
from prospect.security import session_auth
from twenty.api import router as twenty_router
from webprospects.api import router as webprospects_router

# Every route requires a logged-in session unless it opts out with auth=None
# (only login and logout do). The interactive docs list every endpoint, so they
# are limited to staff, who can log in through /admin/.
api = NinjaAPI(auth=session_auth, docs_decorator=staff_member_required)
api.add_router("/", emails_router)
api.add_router("/auth", auth_router)
api.add_router("/twenty", twenty_router)
api.add_router("/webprospects", webprospects_router)

urlpatterns = [
    path('admin/', admin.site.urls),
    # Container healthcheck target. Outside /api/ so it stays reachable even
    # if the Ninja api fails to construct, and unauthenticated so the docker
    # healthcheck needs no credentials.
    path('healthz', health, name='healthz'),
    # Public HTML page for email recipients. Placed under /api/ because nginx
    # already routes that prefix to Django; declared before the Ninja api so it
    # keeps its own plain-Django (non-JSON) handling.
    path('api/unsubscribe/<str:token>', unsubscribe, name='unsubscribe'),
    path('api/', api.urls),
]
