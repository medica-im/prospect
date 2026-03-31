from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI

from emails.api import router as emails_router
from prospect.auth_api import router as auth_router

api = NinjaAPI()
api.add_router("/", emails_router)
api.add_router("/auth", auth_router)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),
]
