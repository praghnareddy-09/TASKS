from django.urls import path

from batches.views import (
    BatchCompleteView,
    BatchCreateView,
    BatchDeleteView,
    BatchDetailView,
    BatchEnrollmentRemoveView,
    BatchEnrollmentView,
    BatchListView,
    BatchUpdateView,
)

app_name = "batches"
urlpatterns = [
    path("", BatchListView.as_view(), name="list"),
    path("new/", BatchCreateView.as_view(), name="create"),
    path("<int:pk>/", BatchDetailView.as_view(), name="detail"),
    path("<int:pk>/enrol/", BatchEnrollmentView.as_view(), name="enrol"),
    path("<int:pk>/trainees/<int:trainee_id>/remove/", BatchEnrollmentRemoveView.as_view(), name="enrollment_remove"),
    path("<int:pk>/edit/", BatchUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", BatchDeleteView.as_view(), name="delete"),
    path("<int:pk>/complete/", BatchCompleteView.as_view(), name="complete"),
]
