from django.urls import path

from accounts.views import (
    LoginView,
    LogoutView,
    PasswordChangeDoneView,
    PasswordChangeView,
    ProfileView,
    RegistrationQueueView,
    RegistrationReviewView,
    RegistrationSubmittedView,
    RegistrationView,
)

app_name = "accounts"
urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("register/", RegistrationView.as_view(), name="register"),
    path("registration-submitted/", RegistrationSubmittedView.as_view(), name="registration_submitted"),
    path("registrations/", RegistrationQueueView.as_view(), name="registration_queue"),
    path("registrations/<int:user_id>/review/", RegistrationReviewView.as_view(), name="registration_review"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("password-change/", PasswordChangeView.as_view(), name="password_change"),
    path("password-change/done/", PasswordChangeDoneView.as_view(), name="password_change_done"),
]
