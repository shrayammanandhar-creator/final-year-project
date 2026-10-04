from django.db import models


class TagKind(models.TextChoices):
    GENDER = "gender", "Gender"
    AGE_GROUP = "age_group", "Age group"
    REGION = "region", "Region"
    FESTIVAL = "festival", "Festival"
    EVENT = "event", "Event"
    OCCASION = "occasion", "Occasion"
    CASTE = "caste", "Caste"
    CATEGORY = "category", "Category"


class Tag(models.Model):
    kind = models.CharField(max_length=32, choices=TagKind.choices, db_index=True)
    name = models.CharField(max_length=64)
    slug = models.SlugField(max_length=80, db_index=True)

    class Meta:
        unique_together = (("kind", "slug"),)
        indexes = [
            models.Index(fields=["kind", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.name}"


class ProductType(models.TextChoices):
    SINGLE = "single", "Single"
    PACKAGE = "package", "Package"


class Product(models.Model):
    sku = models.SlugField(max_length=100, unique=True, blank=True, null=True, db_index=True)
    name = models.CharField(max_length=200, db_index=True)
    type = models.CharField(max_length=16, choices=ProductType.choices, default=ProductType.SINGLE)
    base_price_npr = models.DecimalField(max_digits=12, decimal_places=2, help_text="Stored in NPR")

    tags = models.ManyToManyField(Tag, blank=True, related_name="products")

    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "stock_quantity"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_in_stock(self) -> bool:
        return self.stock_quantity > 0 and self.is_active

    @property
    def stock_alert_message(self) -> str | None:
        if not self.is_active:
            return "Unavailable"
        if self.stock_quantity == 0:
            return "Out of stock"
        if self.stock_quantity <= 3:
            return f"Only {self.stock_quantity} items left"
        return None

    def refresh_availability(self, *, save: bool = True):
        """
        Auto-disable out-of-stock products.
        """
        should_be_active = self.stock_quantity > 0
        if self.is_active != should_be_active:
            self.is_active = should_be_active
            if save:
                self.save(update_fields=["is_active", "updated_at"])


def product_image_upload_to(instance: "ProductImage", filename: str) -> str:
    return f"products/{instance.product_id}/{filename}"


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    # Either upload the image OR provide a source_url to hotlink while prototyping datasets.
    image = models.ImageField(upload_to=product_image_upload_to, blank=True, null=True)
    source_url = models.URLField(blank=True)
    alt_text = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"Image for {self.product}"

# Create your models here.
