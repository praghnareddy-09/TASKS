from django.urls import path

from trainees.views import (
    EnrollmentToggleView,
    TraineeCreateView,
    TraineeDeleteView,
    TraineeDetailView,
    TraineeEnrollmentRemoveView,
    TraineeEnrollmentView,
    TraineeListView,
    TraineePhotoView,
    TraineeActivationToggleView,
    TraineeDeclineView,
    TraineeVerificationView,
    TraineeUpdateView,
)

app_name = "trainees"
urlpatterns = [
    path("", TraineeListView.as_view(), name="list"),
    path("new/", TraineeCreateView.as_view(), name="create"),
    path("photo/<int:pk>/", TraineePhotoView.as_view(), name="photo"),
    path("<int:trainee_id>/verify/", TraineeVerificationView.as_view(), name="verify"),
    path("<int:trainee_id>/decline/", TraineeDeclineView.as_view(), name="decline"),
    path("<int:trainee_id>/toggle-active/", TraineeActivationToggleView.as_view(), name="toggle_active"),
    path("<int:pk>/", TraineeDetailView.as_view(), name="detail"),
    path("<int:trainee_id>/enrol/", TraineeEnrollmentView.as_view(), name="enrol"),
    path("<int:trainee_id>/batches/<int:batch_id>/remove/", TraineeEnrollmentRemoveView.as_view(), name="enrollment_remove"),
    path("<int:pk>/edit/", TraineeUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", TraineeDeleteView.as_view(), name="delete"),
    path("<int:trainee_id>/batches/<int:batch_id>/toggle/", EnrollmentToggleView.as_view(), name="enrollment_toggle"),
]
