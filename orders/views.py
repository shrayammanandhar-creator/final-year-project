from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from products.models import Product
from products.pricing import convert_from_npr, currency_symbol
from products.promotions import discounted_price_npr

from recommendations.signals import log_signal

from .models import Order, OrderItem, OrderStatus
from .context_processors import cart_summary


def _session_cart(request: HttpRequest) -> dict[str, int]:
    cart = request.session.get("nw_cart")
    if not isinstance(cart, dict):
        cart = {}
    # ensure ints
    clean: dict[str, int] = {}
    for k, v in cart.items():
        try:
            clean[str(int(k))] = max(1, int(v))
        except Exception:
            continue
    request.session["nw_cart"] = clean
    return clean


def _currency(request: HttpRequest) -> str:
    if request.user.is_authenticated:
        return (request.user.preferred_currency or "NPR").upper()
    return (request.GET.get("currency") or "NPR").upper()


def _get_or_create_cart_order(user) -> Order:
    order, _ = Order.objects.get_or_create(
        user=user,
        status=OrderStatus.CART,
        defaults={"currency": user.preferred_currency or "NPR"},
    )
    return order


def _quantity_from_request(request: HttpRequest, *, default: int = 1) -> int:
    try:
        quantity = int(request.POST.get("quantity") or default)
    except (TypeError, ValueError):
        quantity = default
    return max(0, min(quantity, 99))


def cart_view(request: HttpRequest) -> HttpResponse:
    currency = _currency(request)
    if request.user.is_authenticated:
        order = _get_or_create_cart_order(request.user)
        items = list(order.items.select_related("product").prefetch_related("product__images"))
        order.sync_currency(currency)
        return render(
            request,
            "orders/cart.html",
            {"order": order, "items": items, "currency": currency, "currency_symbol": currency_symbol(currency)},
        )

    cart = _session_cart(request)
    products = Product.objects.filter(id__in=[int(pid) for pid in cart.keys()], is_active=True).prefetch_related("images")
    rows = []
    total_npr = Decimal("0.00")
    total = Decimal("0.00")
    for p in products:
        qty = cart.get(str(p.id), 1)
        line_npr = discounted_price_npr(p) * qty
        line = convert_from_npr(line_npr, currency)
        rows.append({"product": p, "quantity": qty, "line_total_npr": line_npr, "line_total": line})
        total_npr += line_npr
        total += line
    return render(
        request,
        "orders/cart.html",
        {
            "order": None,
            "items": rows,
            "total_price_npr": total_npr,
            "total_price": total,
            "currency": currency,
            "currency_symbol": currency_symbol(currency),
        },
    )


@require_POST
def add_to_cart(request: HttpRequest, product_id: int) -> HttpResponse:
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    qty = _quantity_from_request(request)
    qty = max(1, min(qty, 99))
    selected_size = (request.POST.get("selected_size") or "").strip()
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or None

    if request.user.is_authenticated:
        order = _get_or_create_cart_order(request.user)
        order.sync_currency(_currency(request))
        item, created = OrderItem.objects.get_or_create(
            order=order,
            product=product,
            defaults={
                "quantity": qty,
                "unit_price_npr": discounted_price_npr(product),
                "unit_price": convert_from_npr(discounted_price_npr(product), order.currency),
            },
        )
        if not created:
            item.quantity = min(99, item.quantity + qty)
            item.save(update_fields=["quantity"])
        order.recalc_totals(save=True)
        log_signal(request.user, product, kind="cart")
        size_note = f" ({selected_size})" if selected_size else ""
        messages.success(request, f"Added {product.name}{size_note} to cart.")
        return redirect(next_url or "orders:cart")

    cart = _session_cart(request)
    pid = str(product.id)
    cart[pid] = min(99, cart.get(pid, 0) + qty)
    request.session.modified = True
    size_note = f" ({selected_size})" if selected_size else ""
    messages.success(request, f"Added {product.name}{size_note} to cart.")
    return redirect(next_url or "orders:cart")


@require_POST
def update_cart_item(request: HttpRequest, product_id: int) -> HttpResponse:
    qty = _quantity_from_request(request)
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or None

    if request.user.is_authenticated:
        order = _get_or_create_cart_order(request.user)
        order.sync_currency(_currency(request))
        item = get_object_or_404(OrderItem, order=order, product_id=product_id)
        if qty == 0:
            item.delete()
        else:
            item.quantity = qty
            item.save(update_fields=["quantity"])
        order.recalc_totals(save=True)
        return redirect(next_url or "orders:cart")

    cart = _session_cart(request)
    pid = str(int(product_id))
    if qty == 0:
        cart.pop(pid, None)
    else:
        cart[pid] = qty
    request.session.modified = True
    return redirect(next_url or "orders:cart")


def cart_offcanvas_fragment(request: HttpRequest) -> HttpResponse:
    """
    Returns just the offcanvas cart HTML fragment (used by fetch/AJAX refresh).
    """
    ctx = cart_summary(request)
    return render(request, "orders/partials/cart_offcanvas.html", ctx)


@require_POST
def update_cart_item_offcanvas(request: HttpRequest, product_id: int) -> HttpResponse:
    """
    Updates a cart item and returns the refreshed offcanvas fragment.
    """
    qty = _quantity_from_request(request)

    if request.user.is_authenticated:
        order = _get_or_create_cart_order(request.user)
        order.sync_currency(_currency(request))
        item = get_object_or_404(OrderItem, order=order, product_id=product_id)
        if qty == 0:
            item.delete()
        else:
            item.quantity = qty
            item.save(update_fields=["quantity"])
        order.recalc_totals(save=True)
    else:
        cart = _session_cart(request)
        pid = str(int(product_id))
        if qty == 0:
            cart.pop(pid, None)
        else:
            cart[pid] = qty
        request.session.modified = True

    ctx = cart_summary(request)
    return render(request, "orders/partials/cart_offcanvas.html", ctx)


@require_POST
def checkout(request: HttpRequest) -> HttpResponse:
    """
    Skeleton checkout:
    - Forces login
    - Marks cart as placed and sets order_date
    """
    if not request.user.is_authenticated:
        return redirect(f"{reverse('users:login')}?next={reverse('orders:checkout')}")

    with transaction.atomic():
        order = Order.objects.select_for_update().filter(
            user=request.user, status=OrderStatus.CART
        ).first()
        if order is None:
            messages.info(request, "Your cart is empty.")
            return redirect("orders:cart")

        items = list(order.items.select_related("product").select_for_update())
        if not items:
            messages.info(request, "Your cart is empty.")
            return redirect("orders:cart")

        product_ids = [item.product_id for item in items]
        products = {
            product.id: product
            for product in Product.objects.select_for_update().filter(id__in=product_ids)
        }
        for item in items:
            product = products.get(item.product_id)
            if product is None or not product.is_active or product.stock_quantity < item.quantity:
                messages.error(request, f"Not enough stock for {item.product.name}.")
                return redirect("orders:cart")

        order.sync_currency(_currency(request), save=False)
        for item in items:
            product = products[item.product_id]
            product.stock_quantity -= item.quantity
            product.refresh_availability(save=False)
            product.save(update_fields=["stock_quantity", "is_active", "updated_at"])
            log_signal(request.user, product, kind="purchase")

        order.status = OrderStatus.PLACED
        order.order_date = timezone.now()
        order.save(update_fields=["status", "order_date", "currency", "total_price", "total_price_npr", "updated_at"])

    messages.success(request, "Order placed. We will confirm shipping, sizing, and payment details before dispatch.")
    return render(request, "orders/order_confirmation.html", {"order": order})
