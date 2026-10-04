from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("NepWears profile", {"fields": ("location", "preferred_currency", "age", "gender", "created_at")}),
    )
    readonly_fields = ("created_at",)
    list_display = ("username", "email", "location", "preferred_currency", "is_staff", "is_active")
    list_filter = ("preferred_currency", "is_staff", "is_active")
