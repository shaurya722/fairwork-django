from django.urls import path

from . import views

urlpatterns = [
    path("chat/", views.ChatAPIView.as_view(), name="chat"),
    path("chat/history/", views.ChatHistoryView.as_view(), name="chat-history"),
    path("chat/sessions/", views.ChatSessionsView.as_view(), name="chat-sessions"),
    path("chat/sessions/<str:session_id>/", views.DeleteSessionView.as_view(), name="chat-session-delete"),
    path("ndis-chat/", views.NDISChatAPIView.as_view(), name="ndis-chat"),
    path("ndis-documents/", views.NDISDocumentsView.as_view(), name="ndis-documents"),
    path("shift-calc/", views.ShiftCalcAPIView.as_view(), name="shift-calc"),
    path("scrape/", views.ScrapeAwardView.as_view(), name="scrape"),
    path("health/", views.HealthView.as_view(), name="health"),
]
