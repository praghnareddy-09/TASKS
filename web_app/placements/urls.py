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
    MyCompanyView,
)

app_name = "placements"
urlpatterns = [
    path("my/", MyPlacementListView.as_view(), name="my_list"),
    path("my/new/", MyPlacementCreateView.as_view(), name="my_create"),
    path("my/<int:pk>/edit/", MyPlacementUpdateView.as_view(), name="my_update"),
    path("my-company/", MyCompanyView.as_view(), name="my_company"),
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
