from decimal import Decimal
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from products.models import Product, Tag, TagKind
from recommendations.models import SignalKind, UserProductSignal

from .models import Order, OrderItem, OrderStatus


class CartAndCheckoutWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="shopper", email="shopper@example.com", password="SafePass123!"
        )
        self.product = Product.objects.create(
            name="Daura Suruwal", sku="test-daura", base_price_npr=Decimal("1000.00"),
            stock_quantity=3, is_active=True,
        )

    def test_anonymous_cart_merges_after_login(self):
        self.client.post(reverse("orders:add_to_cart", args=[self.product.id]), {"quantity": 2})
        response = self.client.post(reverse("users:login"), {
            "username": self.user.username,
            "password": "SafePass123!",
            "next": reverse("orders:cart"),
        })

        self.assertRedirects(response, reverse("orders:cart"))
        order = Order.objects.get(user=self.user, status=OrderStatus.CART)
        self.assertEqual(order.items.get(product=self.product).quantity, 2)
        self.assertEqual(self.client.session.get("nw_cart"), {})

    def test_checkout_requires_post_and_reduces_stock_once(self):
        self.client.force_login(self.user)
        self.client.post(reverse("orders:add_to_cart", args=[self.product.id]), {"quantity": 2})

        self.assertEqual(self.client.get(reverse("orders:checkout")).status_code, 405)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)

        response = self.client.post(reverse("orders:checkout"))
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 1)
        self.assertTrue(self.product.is_active)
        order = Order.objects.get(user=self.user, status=OrderStatus.PLACED)
        self.assertEqual(order.items.get(product=self.product).quantity, 2)
        self.assertTrue(UserProductSignal.objects.filter(
            user=self.user, product=self.product, kind=SignalKind.PURCHASE
        ).exists())

    def test_insufficient_stock_leaves_cart_and_inventory_unchanged(self):
        self.client.force_login(self.user)
        self.client.post(reverse("orders:add_to_cart", args=[self.product.id]), {"quantity": 3})
        self.product.stock_quantity = 2
        self.product.save(update_fields=["stock_quantity"])

        response = self.client.post(reverse("orders:checkout"))
        self.assertRedirects(response, reverse("orders:cart"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 2)
        self.assertTrue(Order.objects.filter(user=self.user, status=OrderStatus.CART).exists())

    def test_invalid_quantity_does_not_raise_and_mutations_reject_get(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("orders:add_to_cart", args=[self.product.id])).status_code, 405)
        self.client.post(reverse("orders:add_to_cart", args=[self.product.id]), {"quantity": "not-a-number"})
        order = Order.objects.get(user=self.user, status=OrderStatus.CART)
        self.assertEqual(order.items.get(product=self.product).quantity, 1)

        response = self.client.post(reverse("orders:update_cart_item", args=[self.product.id]), {"quantity": "bad"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(order.items.get(product=self.product).quantity, 1)

    def test_changing_currency_reprices_cart_totals(self):
        self.client.force_login(self.user)
        self.client.post(reverse("orders:add_to_cart", args=[self.product.id]), {"quantity": 2})
        self.user.preferred_currency = "USD"
        self.user.save(update_fields=["preferred_currency"])

        self.client.get(reverse("orders:cart"))
        order = Order.objects.get(user=self.user, status=OrderStatus.CART)
        self.assertEqual(order.currency, "USD")
        self.assertEqual(order.total_price_npr, Decimal("2000.00"))
        # Unit prices are rounded to cents before line totals are calculated.
        self.assertEqual(order.total_price, Decimal("15.16"))

    def test_active_sale_price_matches_product_view_and_cart(self):
        festival = Tag.objects.create(kind=TagKind.FESTIVAL, name="Test Festival", slug="test-festival")
        self.product.tags.add(festival)
        event_data = [{
            "name": "Test Festival",
            "kind": "festival",
            "date_ad": (date.today() + timedelta(days=1)).isoformat(),
            "tag_slug": "test-festival",
            "discount_percent": 20,
        }]
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "events_ad.json").write_text(json.dumps(event_data), encoding="utf-8")
            with override_settings(NW_DATA_DIR=data_dir):
                self.client.force_login(self.user)
                response = self.client.get(reverse("products:detail", args=[self.product.id]))
                self.assertContains(response, "800.00")
                self.client.post(reverse("orders:add_to_cart", args=[self.product.id]), {"quantity": 2})
                order = Order.objects.get(user=self.user, status=OrderStatus.CART)
                item = order.items.get(product=self.product)
                self.assertEqual(item.unit_price_npr, Decimal("800.00"))
                self.assertEqual(item.line_total_npr, Decimal("1600.00"))
