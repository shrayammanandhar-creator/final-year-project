from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("line_total", "line_total_npr")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "currency", "total_price", "total_price_npr", "created_at")
    list_filter = ("status", "currency", "created_at")
    search_fields = ("id", "user__username", "user__email")
    inlines = [OrderItemInline]
