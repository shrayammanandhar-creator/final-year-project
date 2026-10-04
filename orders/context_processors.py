from __future__ import annotations

from decimal import Decimal

from django.http import HttpRequest

from products.models import Product
from products.pricing import convert_from_npr, currency_symbol
from products.promotions import discounted_price_npr

from .models import Order, OrderStatus


def _currency(request: HttpRequest) -> str:
    if request.user.is_authenticated:
        return (request.user.preferred_currency or "NPR").upper()
    return (request.GET.get("currency") or "NPR").upper()


def cart_summary(request: HttpRequest):
    """
    Adds cart info to every page so we can render an offcanvas cart.
    Works for both authenticated users (Order CART) and anonymous users (session cart).
    """
    currency = _currency(request)

    # Authenticated cart
    if request.user.is_authenticated:
        order, _ = Order.objects.get_or_create(
            user=request.user,
            status=OrderStatus.CART,
            defaults={"currency": request.user.preferred_currency},
        )
        items = list(order.items.select_related("product").prefetch_related("product__images"))
        order.sync_currency(currency)
        count = sum(int(i.quantity) for i in items)
        return {
            "nw_cart_currency": currency,
            "nw_cart_currency_symbol": currency_symbol(currency),
            "nw_cart_items": items,
            "nw_cart_total": order.total_price,
            "nw_cart_count": count,
            "nw_cart_is_empty": count == 0,
        }

    # Anonymous/session cart
    cart = request.session.get("nw_cart")
    if not isinstance(cart, dict):
        cart = {}

    clean: dict[str, int] = {}
    for k, v in cart.items():
        try:
            clean[str(int(k))] = max(1, int(v))
        except Exception:
            continue
    request.session["nw_cart"] = clean

    products = (
        Product.objects.filter(id__in=[int(pid) for pid in clean.keys()], is_active=True)
        .prefetch_related("images")
        .all()
    )
    rows = []
    total = Decimal("0.00")
    count = 0
    for p in products:
        qty = int(clean.get(str(p.id), 1))
        line_total = convert_from_npr(discounted_price_npr(p) * qty, currency)
        rows.append({"product": p, "quantity": qty, "line_total": line_total})
        total += line_total
        count += qty

    return {
        "nw_cart_currency": currency,
        "nw_cart_currency_symbol": currency_symbol(currency),
        "nw_cart_items": rows,
        "nw_cart_total": total,
        "nw_cart_count": count,
        "nw_cart_is_empty": count == 0,
    }
