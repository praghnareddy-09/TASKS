from django.contrib import admin

from batches.models import Batch


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("batch_number", "name", "course", "trainer", "start_date", "end_date", "status")
    list_filter = ("status", "trainer", "start_date")
    search_fields = ("batch_number", "name", "course", "trainer__username", "trainer__first_name", "trainer__last_name")
