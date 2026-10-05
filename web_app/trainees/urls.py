from django.urls import path

from trainees.views import EnrollmentToggleView, TraineeCreateView, TraineeDeleteView, TraineeDetailView, TraineeListView, TraineeUpdateView

app_name = "trainees"
urlpatterns = [
    path("", TraineeListView.as_view(), name="list"),
    path("new/", TraineeCreateView.as_view(), name="create"),
    path("<int:pk>/", TraineeDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", TraineeUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", TraineeDeleteView.as_view(), name="delete"),
    path("<int:trainee_id>/batches/<int:batch_id>/toggle/", EnrollmentToggleView.as_view(), name="enrollment_toggle"),
]
