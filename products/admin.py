from django.contrib import admin

from .models import Product, ProductImage, Tag


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("kind", "name", "slug")
    list_filter = ("kind",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "type", "base_price_npr", "stock_quantity", "is_active", "stock_warning")
    list_filter = ("type", "is_active", "tags__kind")
    search_fields = ("name", "sku", "tags__name")
    filter_horizontal = ("tags",)
    inlines = [ProductImageInline]

    actions = ["disable_out_of_stock"]

    def stock_warning(self, obj: Product):
        return obj.stock_alert_message or ""

    stock_warning.short_description = "Stock alert"

    @admin.action(description="Auto-disable out-of-stock products")
    def disable_out_of_stock(self, request, queryset):
        for product in queryset:
            product.refresh_availability(save=True)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.refresh_availability(save=True)
