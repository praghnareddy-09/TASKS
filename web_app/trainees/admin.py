from django.contrib import admin

from trainees.models import Enrollment, Trainee


@admin.register(Trainee)
class TraineeAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "status", "joined_on")
    list_filter = ("status", "joined_on")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email", "phone")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("trainee", "batch", "enrolled_on")
    list_filter = ("batch", "enrolled_on")
    search_fields = ("trainee__user__username", "batch__name")
