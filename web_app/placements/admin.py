from django.contrib import admin

from placements.models import Placement


@admin.register(Placement)
class PlacementAdmin(admin.ModelAdmin):
    list_display = ("trainee", "company_name", "hr_name", "batch", "status", "verified", "offer_date")
    search_fields = ("trainee__user__username", "trainee__user__first_name", "trainee__user__last_name", "company_name", "hr_name")
    list_filter = ("status", "verified", "batch", "offer_date")
    list_select_related = ("trainee__user", "batch", "verified_by")
