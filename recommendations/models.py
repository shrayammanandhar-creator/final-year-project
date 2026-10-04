from django.conf import settings
from django.db import models


class ProductView(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="product_views"
    )
    product = models.ForeignKey(
        "products.Product", on_delete=models.CASCADE, related_name="views"
    )
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-viewed_at"]),
            models.Index(fields=["product", "-viewed_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} viewed {self.product}"


class SignalKind(models.TextChoices):
    VIEW = "view", "View"
    CART = "cart", "Add to cart"
    PURCHASE = "purchase", "Purchase"


class UserProductSignal(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="signals"
    )
    product = models.ForeignKey(
        "products.Product", on_delete=models.CASCADE, related_name="signals"
    )
    kind = models.CharField(max_length=16, choices=SignalKind.choices, db_index=True)
    created_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["user", "kind", "-created_at"]),
            models.Index(fields=["product", "kind", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} {self.kind} {self.product}"

