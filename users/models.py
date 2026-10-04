from django.contrib.auth.models import AbstractUser
from django.db import models


class Currency(models.TextChoices):
    NPR = "NPR", "NPR (₨)"
    USD = "USD", "USD ($)"
    EUR = "EUR", "EUR (€)"


class User(AbstractUser):
    email = models.EmailField(blank=False)
    location = models.CharField(max_length=120, blank=True, help_text="Country/City abroad")
    preferred_currency = models.CharField(
        max_length=3, choices=Currency.choices, default=Currency.NPR
    )
    age = models.PositiveIntegerField(null=True, blank=True)

    class Gender(models.TextChoices):
        MEN = "men", "Men"
        WOMEN = "women", "Women"
        OTHER = "other", "Other"

    gender = models.CharField(max_length=16, choices=Gender.choices, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.username

    @property
    def purchase_history(self):
        """
        Derived from orders; kept as a convenience API for future recommendations.
        """
        return self.orders.exclude(status="cart").order_by("-created_at")


# Re-export so Django loads the model when importing users.models
from .wishlist_models import WishlistItem  # noqa: E402,F401
