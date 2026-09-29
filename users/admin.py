from django.contrib import admin
from .models import ApprovedEmail

@admin.register(ApprovedEmail)
class ApprovedEmailAdmin(admin.ModelAdmin):
    list_display = ("email", "role", "active", "created_at")
    list_filter = ("role", "active")
    search_fields = ("email",)

