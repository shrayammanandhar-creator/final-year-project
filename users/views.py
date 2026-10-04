from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import LoginForm, SignupForm
from .models import Currency, User, WishlistItem
from orders.models import Order, OrderItem, OrderStatus
from products.pricing import convert_from_npr
from products.promotions import discounted_price_npr
from products.models import Product
from recommendations.services import recommend_for_user


def _redirect_back(request, fallback="products:home"):
    return redirect(_safe_next_url(request, fallback=fallback))


def _strip_modal_params(url: str) -> str:
    """
    Prevent auth modals from reopening after successful actions by stripping
    modal-control query params.
    """
    try:
        parts = urlsplit(url)
        q = [(k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=True) if k not in {"auth", "login_error", "signup_success", "signup_error"}]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))
    except Exception:
        return url


def _with_modal_params(url: str, **params) -> str:
    try:
        parts = urlsplit(url or reverse("products:home"))
        query = [(k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=True) if k not in {"auth", "login_error", "signup_success", "signup_error"}]
        query.extend((k, str(v)) for k, v in params.items() if v is not None)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    except Exception:
        return reverse("products:home")


def _next_url(request) -> str:
    return _safe_next_url(request)


def _safe_next_url(request, *, fallback="products:home", fallback_url: str | None = None) -> str:
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return fallback_url or reverse(fallback)


def _form_error_text(form) -> str:
    errors = []
    for field, field_errors in form.errors.items():
        label = "Form" if field == "__all__" else form.fields.get(field).label or field.replace("_", " ").title()
        for error in field_errors:
            errors.append(f"{label}: {error}")
    return " ".join(errors) or "Please check the form and try again."


def _session_wishlist(request) -> set[int]:
    raw = request.session.get("nw_wishlist")
    if not isinstance(raw, list):
        raw = []
    clean = set()
    for value in raw:
        try:
            clean.add(int(value))
        except Exception:
            continue
    request.session["nw_wishlist"] = sorted(clean)
    return clean


def login_modal(request):
    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            request.session.pop("nw_login_error", None)
            request.session.pop("nw_signup_error", None)

            # Merge anonymous session cart into the authenticated cart.
            sess_cart = request.session.get("nw_cart")
            if isinstance(sess_cart, dict) and sess_cart:
                order, _ = Order.objects.get_or_create(
                    user=user,
                    status=OrderStatus.CART,
                    defaults={"currency": user.preferred_currency or "NPR"},
                )
                for k, v in sess_cart.items():
                    try:
                        pid = int(k)
                        qty = max(1, min(99, int(v)))
                    except Exception:
                        continue
                    try:
                        product = Product.objects.get(pk=pid, is_active=True)
                    except Product.DoesNotExist:
                        continue
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
                request.session["nw_cart"] = {}
                request.session.modified = True

            sess_wishlist = _session_wishlist(request)
            if sess_wishlist:
                products = Product.objects.filter(pk__in=sess_wishlist, is_active=True)
                for product in products:
                    WishlistItem.objects.get_or_create(user=user, product=product)
                request.session["nw_wishlist"] = []
                request.session.modified = True

            next_url = _next_url(request)
            next_url = _strip_modal_params(next_url)
            # Let the UI show a small success message inline (no modal reopen).
            messages.success(request, "Sign in successful.")
            return redirect(next_url)
        # Show this error inside the login modal (not as a global flash message).
        request.session["nw_login_error"] = _form_error_text(form)
        return redirect(_with_modal_params(_next_url(request), auth="login", login_error=1))
    return redirect(_with_modal_params(_next_url(request), auth="login"))


def signup_modal(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            form.save()
            request.session.pop("nw_signup_error", None)
            request.session.pop("nw_login_error", None)
            # Show account-created message inside login modal.
            return redirect(_with_modal_params(_next_url(request), auth="login", signup_success=1))
        # Keep errors inside signup modal (not global flashes).
        request.session["nw_signup_error"] = _form_error_text(form)
        return redirect(_with_modal_params(_next_url(request), auth="signup", signup_error=1))
    return redirect(_with_modal_params(_next_url(request), auth="signup"))


def dashboard(request):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('products:home')}?auth=login")

    if request.method == "POST":
        currency = (request.POST.get("preferred_currency") or "").upper()
        if currency in {"NPR", "USD", "EUR"}:
            request.user.preferred_currency = currency
            request.user.save(update_fields=["preferred_currency"])
            messages.success(request, "Profile updated.")
        return redirect("users:dashboard")

    wishlist = (
        WishlistItem.objects.filter(user=request.user)
        .select_related("product")
        .prefetch_related("product__images")[:100]
    )

    cart_order = (
        Order.objects.filter(user=request.user, status=OrderStatus.CART)
        .prefetch_related("items__product__images")
        .first()
    )
    if cart_order:
        cart_order.sync_currency(request.user.preferred_currency)

    orders = (
        Order.objects.filter(user=request.user)
        .exclude(status=OrderStatus.CART)
        .prefetch_related("items__product__images")[:50]
    )
    recommended = recommend_for_user(request.user, limit=8)
    return render(
        request,
        "users/dashboard.html",
        {
            "wishlist": wishlist,
            "currencies": Currency.choices,
            "cart_order": cart_order,
            "orders": orders,
            "recommended": recommended,
        },
    )


@require_POST
def wishlist_add(request, product_id: int):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    if not request.user.is_authenticated:
        wishlist = _session_wishlist(request)
        wishlist.add(product.id)
        request.session["nw_wishlist"] = sorted(wishlist)
        request.session.modified = True
        messages.success(request, "Saved to wishlist. Sign in later to keep it on your account.")
        return redirect(_safe_next_url(request, fallback_url=reverse("products:detail", args=[product_id])))
    WishlistItem.objects.get_or_create(user=request.user, product=product)
    messages.success(request, "Added to wishlist.")
    return redirect(_safe_next_url(request, fallback_url=reverse("products:detail", args=[product_id])))


@require_POST
def wishlist_remove(request, product_id: int):
    if not request.user.is_authenticated:
        wishlist = _session_wishlist(request)
        wishlist.discard(int(product_id))
        request.session["nw_wishlist"] = sorted(wishlist)
        request.session.modified = True
        messages.success(request, "Removed from wishlist.")
        return redirect(_safe_next_url(request, fallback_url=reverse("products:detail", args=[product_id])))
    WishlistItem.objects.filter(user=request.user, product_id=product_id).delete()
    messages.success(request, "Removed from wishlist.")
    return redirect(_safe_next_url(request, fallback="users:dashboard"))
