from django.urls import path

from . import views

urlpatterns = [
    path("chat/", views.ChatAPIView.as_view(), name="chat"),
    path("chat/history/", views.ChatHistoryView.as_view(), name="chat-history"),
    path("chat/sessions/", views.ChatSessionsView.as_view(), name="chat-sessions"),
    path("scrape/", views.ScrapeAwardView.as_view(), name="scrape"),
    path("health/", views.HealthView.as_view(), name="health"),
]
