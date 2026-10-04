from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from products.models import Product


class OrderStatus(models.TextChoices):
    CART = "cart", "Cart"
    PLACED = "placed", "Placed"
    PAID = "paid", "Paid"
    SHIPPED = "shipped", "Shipped"
    CANCELLED = "cancelled", "Cancelled"


class Order(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders"
    )
    status = models.CharField(max_length=16, choices=OrderStatus.choices, default=OrderStatus.CART)

    currency = models.CharField(max_length=3, default="NPR")
    total_price_npr = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), help_text="Total in selected currency"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    order_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Order #{self.pk} ({self.status})"

    def recalc_totals(self, *, save: bool = True):
        total_npr = Decimal("0.00")
        total = Decimal("0.00")
        for item in self.items.all():
            total_npr += item.line_total_npr
            total += item.line_total
        self.total_price_npr = total_npr
        self.total_price = total
        if save:
            self.save(update_fields=["total_price_npr", "total_price", "updated_at"])

    def sync_currency(self, currency: str, *, save: bool = True) -> None:
        """Keep the cart's stored prices and totals in its display currency."""
        currency = (currency or "NPR").upper()
        if currency not in {"NPR", "USD", "EUR"}:
            currency = "NPR"

        # Import here to avoid a models/pricing import cycle at startup.
        from products.pricing import convert_from_npr
        from products.promotions import discounted_price_npr

        items = list(self.items.select_related("product").prefetch_related("product__tags"))
        for item in items:
            item.unit_price_npr = discounted_price_npr(item.product)
            item.unit_price = convert_from_npr(item.unit_price_npr, currency)
        if items:
            OrderItem.objects.bulk_update(items, ["unit_price_npr", "unit_price"])
        self.currency = currency

        self.recalc_totals(save=False)
        if save:
            self.save(update_fields=["currency", "total_price_npr", "total_price", "updated_at"])


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1)

    unit_price_npr = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("order", "product"),)

    def __str__(self) -> str:
        return f"{self.quantity} × {self.product}"

    @property
    def line_total_npr(self) -> Decimal:
        return (self.unit_price_npr or Decimal("0.00")) * self.quantity

    @property
    def line_total(self) -> Decimal:
        return (self.unit_price or Decimal("0.00")) * self.quantity
