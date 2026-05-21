"""URL configuration for the Fair Work Award chatbot."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("chatbot.urls")),
]
