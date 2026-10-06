from django.urls import path

from placements.views import (
    MyPlacementCreateView,
    MyPlacementListView,
    MyPlacementUpdateView,
    PlacementDeleteView,
    PlacementDetailView,
    PlacementFileView,
    PlacementListView,
    PlacementReportView,
    PlacementUpdateView,
    PlacementVerifyView,
    CompanyDetailView,
    CompanyDirectoryView,
)
from placements.application_views import (
    ApplicationCreateView,
    ApplicationDeleteView,
    ApplicationDetailView,
    ApplicationListView,
    ApplicationUpdateView,
    InterviewCreateView,
    InterviewListView,
    InterviewUpdateView,
)

app_name = "placements"
urlpatterns = [
    path("applications/", ApplicationListView.as_view(), name="applications"),
    path("applications/new/", ApplicationCreateView.as_view(), name="application_create"),
    path("applications/<int:pk>/", ApplicationDetailView.as_view(), name="application_detail"),
    path("applications/<int:pk>/edit/", ApplicationUpdateView.as_view(), name="application_update"),
    path("applications/<int:pk>/delete/", ApplicationDeleteView.as_view(), name="application_delete"),
    path("applications/<int:application_id>/interviews/new/", InterviewCreateView.as_view(), name="interview_create"),
    path("interviews/", InterviewListView.as_view(), name="interviews"),
    path("interviews/<int:pk>/edit/", InterviewUpdateView.as_view(), name="interview_update"),
    path("my/", MyPlacementListView.as_view(), name="my_list"),
    path("my/new/", MyPlacementCreateView.as_view(), name="my_create"),
    path("my/<int:pk>/edit/", MyPlacementUpdateView.as_view(), name="my_update"),
    path("", PlacementListView.as_view(), name="list"),
    path("companies/", CompanyDirectoryView.as_view(), name="companies"),
    path("companies/<int:placement_id>/", CompanyDetailView.as_view(), name="company_detail"),
    path("report/", PlacementReportView.as_view(), name="report"),
    path("<int:pk>/", PlacementDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", PlacementUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", PlacementDeleteView.as_view(), name="delete"),
    path("<int:pk>/verify/", PlacementVerifyView.as_view(), name="verify"),
    path("<int:pk>/offer-letter/", PlacementFileView.as_view(), name="offer_letter"),
]
