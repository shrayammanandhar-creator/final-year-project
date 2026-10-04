from __future__ import annotations

from django.db.models import Count, Sum

from .models import OrderItem, OrderStatus


def best_selling_products(limit: int = 10):
    """
    Returns products ordered by quantity sold.
    """
    return (
        OrderItem.objects.filter(order__status__in=[OrderStatus.PLACED, OrderStatus.PAID, OrderStatus.SHIPPED])
        .values("product__id", "product__name")
        .annotate(qty=Sum("quantity"))
        .order_by("-qty")[:limit]
    )


def country_wise_users(limit: int = 10):
    """
    Counts users by their stored location field (placeholder for country-level analytics).
    """
    from users.models import User

    return (
        User.objects.exclude(location="")
        .values("location")
        .annotate(count=Count("id"))
        .order_by("-count")[:limit]
    )

