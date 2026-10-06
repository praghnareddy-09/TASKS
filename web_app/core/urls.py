from django.urls import path

from core.views import (
    AnalyticsView,
    DashboardView,
    OfflineView,
    WorkflowNotificationCountView,
    WorkflowNotificationListView,
    service_worker,
)

app_name = "core"
urlpatterns = [
    path("sw.js", service_worker, name="service_worker"),
    path("offline/", OfflineView.as_view(), name="offline"),
    path("analytics/", AnalyticsView.as_view(), name="analytics"),
    path("notifications/", WorkflowNotificationListView.as_view(), name="notifications"),
    path("notifications/count/", WorkflowNotificationCountView.as_view(), name="notification_count"),
    path("", DashboardView.as_view(), name="dashboard"),
]
